from __future__ import annotations

import re
from collections.abc import Iterable
from hashlib import sha1

from .models import (
    AgentTraceSummary,
    AllergyProfile,
    AllergyTag,
    DishRiskResult,
    EvidenceFragment,
    MenuItem,
    MenuSection,
    MenuSource,
    RecommendedAction,
    RecommendationResult,
    RestaurantContext,
    RiskLevel,
    SourceType,
)


ALLERGEN_TERMS: dict[AllergyTag, tuple[str, ...]] = {
    AllergyTag.DAIRY: ("cream", "cheese", "butter", "yogurt", "whey", "milk", "parmesan"),
    AllergyTag.WHEAT_GLUTEN: ("wheat", "flour", "pasta", "bread", "soy sauce", "gluten"),
    AllergyTag.TREE_NUT: ("almond", "walnut", "cashew", "pistachio", "hazelnut", "pecan", "pesto"),
    AllergyTag.PEANUT: ("peanut", "peanut oil", "satay"),
    AllergyTag.SESAME: ("sesame", "tahini"),
    AllergyTag.SOY: ("soy", "tofu", "edamame", "soy sauce"),
    AllergyTag.EGG: ("egg", "mayo", "aioli"),
    AllergyTag.FISH: ("anchovy", "tuna", "salmon", "cod", "fish"),
    AllergyTag.SHELLFISH: ("shrimp", "crab", "lobster", "scallop", "prawn", "shellfish"),
}

PROMPT_INJECTION_PATTERNS = (
    "ignore previous",
    "disregard previous",
    "system prompt",
    "developer message",
    "you are chatgpt",
    "override these instructions",
    "forget the allergy policy",
)


def analyze_restaurant_context(
    context: RestaurantContext,
    profile: AllergyProfile,
    trace: AgentTraceSummary | None = None,
) -> RecommendationResult:
    trace = trace or AgentTraceSummary()
    trace.tool_calls.append("deterministic_allergen_risk_engine")
    menu_sources = normalize_menu_sources(context.menu_sources)

    if not menu_sources:
        return build_insufficient_result(
            context=context,
            profile=profile,
            trace=trace,
            reason="No official menu, structured menu, or fixture menu was available for analysis.",
        )

    if all(source.source_type == SourceType.REVIEW for source in menu_sources):
        return build_insufficient_result(
            context=context,
            profile=profile,
            trace=trace,
            reason="Only review-derived menu evidence was available; reviews can support warnings but cannot establish a lower-risk recommendation.",
        )

    dish_results: list[DishRiskResult] = []
    for source in menu_sources:
        for section in source.sections:
            for item in section.items:
                dish_results.append(analyze_dish(item, source, context.review_evidence, profile))

    if not dish_results:
        return build_insufficient_result(
            context=context,
            profile=profile,
            trace=trace,
            reason="Menu sources were present, but no dish names or ingredients could be extracted.",
        )

    overall_risk = derive_overall_risk(dish_results)
    confidence = derive_overall_confidence(dish_results, overall_risk)
    missing_information = dedupe(
        missing for result in dish_results for missing in result.missing_information
    )
    recommended_questions = dedupe(
        question for result in dish_results for question in result.recommended_questions
    )
    evidence = dedupe_evidence(fragment for result in dish_results for fragment in result.evidence)
    action = derive_recommended_action(overall_risk)
    trace.abstained = overall_risk == RiskLevel.INSUFFICIENT_EVIDENCE
    trace.routed_to_safety_gate = overall_risk in {RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.INSUFFICIENT_EVIDENCE}

    return RecommendationResult(
        restaurant_id=context.restaurant_id,
        restaurant_name=context.restaurant_name,
        profile=profile,
        overall_risk=overall_risk,
        confidence=confidence,
        summary=build_summary(overall_risk, evidence, missing_information),
        dish_results=dish_results,
        evidence=evidence[:8],
        missing_information=missing_information[:8],
        recommended_questions=recommended_questions[:8],
        recommended_action=action,
        trace=trace,
    )


def normalize_menu_sources(sources: Iterable[MenuSource]) -> list[MenuSource]:
    normalized: list[MenuSource] = []
    for source in sources:
        if source.sections:
            normalized.append(source)
            continue
        if not source.raw_text:
            continue
        sections = parse_raw_menu_text(source.raw_text)
        if sections:
            normalized.append(source.model_copy(update={"sections": sections}))
    return normalized


def parse_raw_menu_text(raw_text: str) -> list[MenuSection]:
    items: list[MenuItem] = []
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line or is_prompt_injection(line):
            continue
        if len(line) > 180:
            continue
        if " - " in line:
            name, description = line.split(" - ", 1)
        elif ": " in line:
            name, description = line.split(": ", 1)
        else:
            continue
        if not name.strip() or not description.strip():
            continue
        items.append(MenuItem(name=name.strip(), description=description.strip()))
    return [MenuSection(title="Extracted menu", items=items)] if items else []


def analyze_dish(
    item: MenuItem,
    source: MenuSource,
    review_evidence: list[EvidenceFragment],
    profile: AllergyProfile,
) -> DishRiskResult:
    selected_allergens = profile.allergens or [AllergyTag.PEANUT]
    haystack = normalized_haystack(item)
    detected = sorted(
        {
            allergen
            for allergen in selected_allergens
            if allergen in item.confirmed_allergens
            or allergen in item.inferred_risks
            or any(term_matches(haystack, term) for term in ALLERGEN_TERMS[allergen])
        },
        key=lambda allergen: allergen.value,
    )
    evidence = build_dish_evidence(item, source, detected)
    missing_information = list(item.unknowns)
    recommended_questions = build_questions(detected, strict_profile(profile))

    has_ingredients = bool((item.description or "").strip()) or bool(item.confirmed_allergens or item.inferred_risks)
    if not has_ingredients:
        missing_information.append(f"{item.name} does not list ingredients.")

    conflict_evidence = find_review_conflicts(item.name, review_evidence, selected_allergens)
    if conflict_evidence:
        evidence.extend(conflict_evidence)
        missing_information.append("Review evidence conflicts with or adds risk beyond the structured menu.")

    if detected:
        return DishRiskResult(
            dish=item.name,
            risk_level=RiskLevel.HIGH,
            confidence=round(min(0.94, 0.72 + source.reliability * 0.2 + len(evidence) * 0.02), 2),
            detected_allergens=detected,
            evidence=evidence,
            missing_information=dedupe(missing_information),
            recommended_questions=recommended_questions,
            recommended_action=RecommendedAction.AVOID,
        )

    if conflict_evidence:
        return DishRiskResult(
            dish=item.name,
            risk_level=RiskLevel.MEDIUM,
            confidence=0.62,
            detected_allergens=[],
            evidence=evidence,
            missing_information=dedupe(missing_information),
            recommended_questions=dedupe(recommended_questions + ["Ask staff to reconcile the menu with allergy-related review warnings."]),
            recommended_action=RecommendedAction.ASK_STAFF,
        )

    if not has_ingredients:
        return DishRiskResult(
            dish=item.name,
            risk_level=RiskLevel.INSUFFICIENT_EVIDENCE,
            confidence=0.2,
            detected_allergens=[],
            evidence=evidence,
            missing_information=dedupe(missing_information),
            recommended_questions=dedupe(recommended_questions + ["Can you confirm the full ingredient list for this dish?"]),
            recommended_action=RecommendedAction.INSUFFICIENT_EVIDENCE,
        )

    if strict_profile(profile):
        return DishRiskResult(
            dish=item.name,
            risk_level=RiskLevel.MEDIUM,
            confidence=0.48,
            detected_allergens=[],
            evidence=evidence,
            missing_information=dedupe(missing_information + ["Cross-contact handling is not confirmed for a strict allergy profile."]),
            recommended_questions=dedupe(recommended_questions + ["Can this be prepared with clean utensils and surfaces away from my allergens?"]),
            recommended_action=RecommendedAction.ASK_STAFF,
        )

    return DishRiskResult(
        dish=item.name,
        risk_level=RiskLevel.LOW,
        confidence=round(min(0.72, 0.42 + source.reliability * 0.25), 2),
        detected_allergens=[],
        evidence=evidence,
        missing_information=dedupe(missing_information + ["Cross-contact handling is not confirmed."]),
        recommended_questions=dedupe(recommended_questions + ["Can you verify ingredients and prep surfaces before I order?"]),
        recommended_action=RecommendedAction.VERIFY,
    )


def build_insufficient_result(
    context: RestaurantContext,
    profile: AllergyProfile,
    trace: AgentTraceSummary,
    reason: str,
) -> RecommendationResult:
    trace.abstained = True
    trace.routed_to_safety_gate = True
    questions = [
        "Can you confirm the full ingredient list for the dish I am considering?",
        "Are shared fryers, utensils, or prep surfaces used with my allergens?",
        "Can the kitchen prepare the item away from my allergens?",
    ]
    return RecommendationResult(
        restaurant_id=context.restaurant_id,
        restaurant_name=context.restaurant_name,
        profile=profile,
        overall_risk=RiskLevel.INSUFFICIENT_EVIDENCE,
        confidence=0.12,
        summary="Insufficient evidence. The available sources do not support a lower-risk dining recommendation.",
        dish_results=[],
        evidence=[],
        missing_information=[reason],
        recommended_questions=questions,
        recommended_action=RecommendedAction.INSUFFICIENT_EVIDENCE,
        trace=trace,
    )


def build_dish_evidence(item: MenuItem, source: MenuSource, detected: list[AllergyTag]) -> list[EvidenceFragment]:
    fragments: list[EvidenceFragment] = []
    text = f"{item.name}: {item.description}" if item.description else item.name
    if detected:
        fragments.append(
            EvidenceFragment(
                id=evidence_id(source, item.name, text),
                source_type=source.source_type,
                source_url=source.source_url,
                source_timestamp=source.source_timestamp,
                dish_name=item.name,
                text=text,
                matched_allergens=detected,
                reliability=source.reliability,
            )
        )
    elif item.description:
        fragments.append(
            EvidenceFragment(
                id=evidence_id(source, item.name, text),
                source_type=source.source_type,
                source_url=source.source_url,
                source_timestamp=source.source_timestamp,
                dish_name=item.name,
                text=text,
                matched_allergens=[],
                reliability=source.reliability,
            )
        )
    return fragments


def find_review_conflicts(
    dish_name: str,
    review_evidence: list[EvidenceFragment],
    selected_allergens: list[AllergyTag],
) -> list[EvidenceFragment]:
    dish_terms = [part for part in re.split(r"\W+", dish_name.lower()) if len(part) >= 4]
    conflicts: list[EvidenceFragment] = []
    for fragment in review_evidence:
        text = fragment.text.lower()
        if dish_terms and not any(term in text for term in dish_terms):
            continue
        matched = [
            allergen
            for allergen in selected_allergens
            if allergen in fragment.matched_allergens
            or any(term_matches(text, term) for term in ALLERGEN_TERMS[allergen])
        ]
        if matched:
            conflicts.append(fragment.model_copy(update={"matched_allergens": matched}))
    return conflicts


def derive_overall_risk(results: list[DishRiskResult]) -> RiskLevel:
    levels = {result.risk_level for result in results}
    if RiskLevel.HIGH in levels:
        return RiskLevel.HIGH
    if RiskLevel.MEDIUM in levels:
        return RiskLevel.MEDIUM
    if levels == {RiskLevel.INSUFFICIENT_EVIDENCE}:
        return RiskLevel.INSUFFICIENT_EVIDENCE
    if RiskLevel.LOW in levels:
        return RiskLevel.LOW
    return RiskLevel.INSUFFICIENT_EVIDENCE


def derive_overall_confidence(results: list[DishRiskResult], risk: RiskLevel) -> float:
    if not results:
        return 0.12
    relevant = [result.confidence for result in results if result.risk_level == risk] or [result.confidence for result in results]
    return round(sum(relevant) / len(relevant), 2)


def derive_recommended_action(risk: RiskLevel) -> RecommendedAction:
    if risk == RiskLevel.HIGH:
        return RecommendedAction.AVOID
    if risk == RiskLevel.MEDIUM:
        return RecommendedAction.ASK_STAFF
    if risk == RiskLevel.LOW:
        return RecommendedAction.VERIFY
    return RecommendedAction.INSUFFICIENT_EVIDENCE


def build_summary(
    risk: RiskLevel,
    evidence: list[EvidenceFragment],
    missing_information: list[str],
) -> str:
    if risk == RiskLevel.HIGH:
        return "High allergen risk was detected from source-backed menu evidence. Avoid unless restaurant staff confirms a suitable alternative."
    if risk == RiskLevel.MEDIUM:
        return "Some options may be lower risk, but missing or conflicting evidence requires staff verification before ordering."
    if risk == RiskLevel.LOW:
        return "Lower-risk option based on listed ingredients, but verify preparation and cross-contact handling with staff."
    if missing_information:
        return "Insufficient evidence. The menu does not list enough ingredient or cross-contact information to assess confidently."
    if evidence:
        return "Insufficient evidence. The available source fragments do not support a lower-risk recommendation."
    return "Insufficient evidence. Ask staff targeted ingredient and preparation questions before ordering."


def build_questions(detected: list[AllergyTag], is_strict: bool) -> list[str]:
    allergen_text = ", ".join(allergen.value.replace("_", " ") for allergen in detected) or "my selected allergens"
    questions = [
        f"Does this dish contain {allergen_text} in the ingredients, sauces, marinades, or garnish?",
        "Are shared fryers, utensils, grills, or prep surfaces used with my allergens?",
    ]
    if is_strict:
        questions.append("Can the kitchen prepare this with clean utensils and surfaces away from my allergens?")
    return questions


def normalized_haystack(item: MenuItem) -> str:
    pieces = [item.name, item.description or ""]
    pieces.extend(allergen.value.replace("_", " ") for allergen in item.confirmed_allergens)
    pieces.extend(allergen.value.replace("_", " ") for allergen in item.inferred_risks)
    return " ".join(pieces).lower()


def term_matches(text: str, term: str) -> bool:
    if " " in term:
        return term in text
    return re.search(rf"\b{re.escape(term)}s?\b", text) is not None


def strict_profile(profile: AllergyProfile) -> bool:
    text = f"{profile.sensitivity} {profile.prep_preference}".lower()
    return any(value in text for value in ("strict", "severe", "celiac", "anaphylaxis"))


def is_prompt_injection(text: str) -> bool:
    lowered = text.lower()
    return any(pattern in lowered for pattern in PROMPT_INJECTION_PATTERNS)


def evidence_id(source: MenuSource, dish_name: str, text: str) -> str:
    digest = sha1(f"{source.source_type}:{source.source_url}:{dish_name}:{text}".encode("utf-8")).hexdigest()
    return digest[:12]


def dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def dedupe_evidence(values: Iterable[EvidenceFragment]) -> list[EvidenceFragment]:
    seen: set[str] = set()
    output: list[EvidenceFragment] = []
    for value in values:
        if value.id in seen:
            continue
        seen.add(value.id)
        output.append(value)
    return output
