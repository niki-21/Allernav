from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable

from .models import AllergyTag, ImpactDirection, PlaceScoreSummary, ReviewEvidence, SignalType, Verdict


ALLERGY_LABELS = {
    AllergyTag.PEANUT: "peanut",
    AllergyTag.TREE_NUT: "tree nut",
    AllergyTag.DAIRY: "dairy",
    AllergyTag.EGG: "egg",
    AllergyTag.SHELLFISH: "shellfish",
    AllergyTag.FISH: "fish",
    AllergyTag.SOY: "soy",
    AllergyTag.SESAME: "sesame",
    AllergyTag.WHEAT_GLUTEN: "wheat/gluten",
}

ALLERGY_SYNONYMS = {
    AllergyTag.PEANUT: ["peanut", "peanuts", "peanut oil"],
    AllergyTag.TREE_NUT: ["tree nut", "tree nuts", "almond", "walnut", "cashew", "pecan", "pistachio", "hazelnut"],
    AllergyTag.DAIRY: ["dairy", "milk", "butter", "cheese", "cream", "lactose"],
    AllergyTag.EGG: ["egg", "eggs", "egg wash"],
    AllergyTag.SHELLFISH: ["shellfish", "shrimp", "prawn", "lobster", "crab", "scallop"],
    AllergyTag.FISH: ["fish", "salmon", "tuna", "anchovy", "cod"],
    AllergyTag.SOY: ["soy", "soybean", "soy sauce", "tofu", "edamame"],
    AllergyTag.SESAME: ["sesame", "tahini"],
    AllergyTag.WHEAT_GLUTEN: ["gluten", "wheat", "celiac", "gluten free", "gluten-free"],
}

GENERIC_ALLERGY_TERMS = [
    "allergy",
    "allergic",
    "allergen",
    "cross contact",
    "cross-contact",
    "cross contamination",
    "cross-contamination",
    "separate fryer",
    "dedicated fryer",
]

NEGATIVE_OVERRIDES = [
    "not allergy friendly",
    "not allergy-friendly",
    "no allergy menu",
    "staff did not understand",
    "staff didn't understand",
    "could not guarantee",
    "couldn't guarantee",
    "shared fryer",
    "same fryer",
    "had a reaction",
    "got sick",
]


@dataclass(frozen=True)
class SignalConfig:
    signal_type: SignalType
    impact: ImpactDirection
    label: str
    phrases: tuple[str, ...]
    base_weight: float


@dataclass(frozen=True)
class DetectedSignal:
    signal_type: SignalType
    impact: ImpactDirection
    label: str
    matched_phrase: str
    matched_allergens: list[AllergyTag]
    weight: float


POSITIVE_SIGNALS: tuple[SignalConfig, ...] = (
    SignalConfig(
        signal_type=SignalType.ACCOMMODATION,
        impact=ImpactDirection.POSITIVE,
        label="Strong allergy accommodations",
        phrases=(
            "allergy friendly",
            "allergy-friendly",
            "felt safe",
            "safe for my allergy",
            "safe for allergies",
            "accommodating",
            "took my allergy seriously",
            "careful with my allergy",
            "dedicated fryer",
            "separate fryer",
            "separate prep",
        ),
        base_weight=1.2,
    ),
    SignalConfig(
        signal_type=SignalType.STAFF_KNOWLEDGE,
        impact=ImpactDirection.POSITIVE,
        label="Knowledgeable staff",
        phrases=(
            "staff understood",
            "server understood",
            "manager understood",
            "knowledgeable about allergies",
            "answered all my questions",
            "double checked",
            "checked with the kitchen",
            "reassured me",
        ),
        base_weight=1.0,
    ),
    SignalConfig(
        signal_type=SignalType.MENU_LABELING,
        impact=ImpactDirection.POSITIVE,
        label="Clear menu labeling",
        phrases=(
            "allergy menu",
            "clearly labeled",
            "labeled allergens",
            "marked gluten free",
            "marked gluten-free",
            "gluten free options",
            "gluten-free options",
        ),
        base_weight=0.9,
    ),
)

NEGATIVE_SIGNALS: tuple[SignalConfig, ...] = (
    SignalConfig(
        signal_type=SignalType.UNCERTAINTY,
        impact=ImpactDirection.NEGATIVE,
        label="Explicitly not allergy-friendly",
        phrases=(
            "not allergy friendly",
            "not allergy-friendly",
        ),
        base_weight=1.7,
    ),
    SignalConfig(
        signal_type=SignalType.REACTION_REPORT,
        impact=ImpactDirection.NEGATIVE,
        label="Reported allergic reaction",
        phrases=(
            "had a reaction",
            "got sick",
            "anaphylaxis",
            "epi pen",
            "epipen",
            "hives",
            "threw up",
            "vomited",
            "itchy after eating",
        ),
        base_weight=2.2,
    ),
    SignalConfig(
        signal_type=SignalType.CROSS_CONTACT_RISK,
        impact=ImpactDirection.NEGATIVE,
        label="Cross-contact risk mentioned",
        phrases=(
            "cross contamination",
            "cross-contamination",
            "cross contact",
            "cross-contact",
            "shared fryer",
            "same fryer",
            "not safe",
            "unsafe",
            "contaminated",
        ),
        base_weight=1.6,
    ),
    SignalConfig(
        signal_type=SignalType.UNCERTAINTY,
        impact=ImpactDirection.NEGATIVE,
        label="Uncertain allergy handling",
        phrases=(
            "didn't know",
            "did not know",
            "not sure",
            "uncertain",
            "couldn't answer",
            "could not answer",
            "couldn't guarantee",
            "could not guarantee",
            "wouldn't recommend",
            "be careful",
        ),
        base_weight=1.1,
    ),
)


def analyze_place(place: dict[str, Any], allergens: Iterable[AllergyTag]) -> tuple[PlaceScoreSummary, list[ReviewEvidence], str]:
    selected_allergens = list(dict.fromkeys(allergens))
    if not selected_allergens:
        selected_allergens = [AllergyTag.PEANUT]

    evidence_items: list[ReviewEvidence] = []
    positive_counter: Counter[str] = Counter()
    negative_counter: Counter[str] = Counter()
    positive_total = 0.0
    negative_total = 0.0
    specific_mentions = 0
    severe_negative = False

    for review in place.get("reviews", []):
        review_text = (review.get("text") or "").strip()
        if not review_text:
            continue

        detected = detect_signals(review_text, review.get("rating"), review.get("publish_time"), selected_allergens)
        for signal in detected:
            evidence = ReviewEvidence(
                review_id=review.get("review_id", "review"),
                author_name=review.get("author_name"),
                rating=review.get("rating"),
                text=review_text,
                matched_allergens=signal.matched_allergens,
                signal_type=signal.signal_type,
                impact=signal.impact,
                excerpt=build_excerpt(review_text, signal.matched_phrase),
                weight=round(signal.weight, 2),
                publish_time=review.get("publish_time"),
            )
            evidence_items.append(evidence)
            if signal.impact == ImpactDirection.POSITIVE:
                positive_total += signal.weight
                positive_counter[signal.label] += 1
            else:
                negative_total += signal.weight
                negative_counter[signal.label] += 1
            if signal.matched_allergens:
                specific_mentions += 1
            if signal.signal_type == SignalType.REACTION_REPORT and signal.impact == ImpactDirection.NEGATIVE:
                severe_negative = True

    evidence_items.sort(key=lambda item: item.weight, reverse=True)
    evidence_items = evidence_items[:8]
    evidence_count = len(evidence_items)

    score = compute_score(
        rating=place.get("rating"),
        positive_total=positive_total,
        negative_total=negative_total,
        evidence_count=evidence_count,
    )
    confidence = compute_confidence(evidence_count, specific_mentions)
    verdict = derive_verdict(score, confidence, evidence_count, severe_negative)
    summary = PlaceScoreSummary(
        score=score,
        verdict=verdict,
        confidence=round(confidence, 2),
        positive_signals=[label for label, _ in positive_counter.most_common(3)],
        negative_signals=[label for label, _ in negative_counter.most_common(3)],
        evidence_count=evidence_count,
    )
    explanation = build_explanation(summary, selected_allergens, evidence_items)
    return summary, evidence_items, explanation


def detect_signals(
    review_text: str,
    rating: float | None,
    publish_time: str | None,
    selected_allergens: list[AllergyTag],
) -> list[DetectedSignal]:
    normalized = normalize_text(review_text)
    matched_allergens = find_allergens(normalized, selected_allergens)
    generic_allergy_context = any(term in normalized for term in GENERIC_ALLERGY_TERMS)
    signals: list[DetectedSignal] = []

    for config in NEGATIVE_SIGNALS:
        phrase = find_phrase(normalized, config.phrases)
        if phrase:
            if config.signal_type == SignalType.UNCERTAINTY and any(
                existing.signal_type in {SignalType.REACTION_REPORT, SignalType.CROSS_CONTACT_RISK}
                for existing in signals
            ):
                continue
            signals.append(
                build_signal(config, phrase, matched_allergens, generic_allergy_context, rating, publish_time)
            )

    for config in POSITIVE_SIGNALS:
        phrase = find_phrase(normalized, config.phrases)
        if phrase and not any(override in normalized for override in NEGATIVE_OVERRIDES):
            signals.append(
                build_signal(config, phrase, matched_allergens, generic_allergy_context, rating, publish_time)
            )

    if not signals and generic_allergy_context and matched_allergens:
        signals.append(
            build_signal(
                SignalConfig(
                    signal_type=SignalType.UNCERTAINTY,
                    impact=ImpactDirection.NEGATIVE,
                    label="Allergy mentioned without clear safeguards",
                    phrases=("allergy",),
                    base_weight=0.6,
                ),
                "allergy",
                matched_allergens,
                generic_allergy_context,
                rating,
                publish_time,
            )
        )

    deduped: dict[tuple[SignalType, ImpactDirection, str], DetectedSignal] = {}
    for signal in signals:
        key = (signal.signal_type, signal.impact, signal.matched_phrase)
        current = deduped.get(key)
        if current is None or signal.weight > current.weight:
            deduped[key] = signal
    return list(deduped.values())


def build_signal(
    config: SignalConfig,
    matched_phrase: str,
    matched_allergens: list[AllergyTag],
    generic_allergy_context: bool,
    rating: float | None,
    publish_time: str | None,
) -> DetectedSignal:
    specificity_multiplier = 1.35 if matched_allergens else 0.78 if generic_allergy_context else 0.0
    rating_multiplier = 1.0
    if rating is not None:
        if config.impact == ImpactDirection.POSITIVE:
            rating_multiplier = 1.08 if rating >= 4 else 0.92
        else:
            rating_multiplier = 1.12 if rating <= 2 else 1.0

    recency_multiplier = 1.0
    if publish_time:
        try:
            published = datetime.fromisoformat(publish_time.replace("Z", "+00:00"))
            age_days = (datetime.now(UTC) - published.astimezone(UTC)).days
            if age_days <= 365:
                recency_multiplier = 1.08
            elif age_days > 365 * 3:
                recency_multiplier = 0.9
        except ValueError:
            pass

    return DetectedSignal(
        signal_type=config.signal_type,
        impact=config.impact,
        label=config.label,
        matched_phrase=matched_phrase,
        matched_allergens=matched_allergens,
        weight=config.base_weight * specificity_multiplier * rating_multiplier * recency_multiplier,
    )


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def find_allergens(text: str, selected_allergens: list[AllergyTag]) -> list[AllergyTag]:
    matches: list[AllergyTag] = []
    for allergen in selected_allergens:
        if any(term in text for term in ALLERGY_SYNONYMS[allergen]):
            matches.append(allergen)
    return matches


def find_phrase(text: str, phrases: tuple[str, ...]) -> str | None:
    for phrase in phrases:
        if phrase in text:
            return phrase
    return None


def build_excerpt(text: str, phrase: str, max_chars: int = 170) -> str:
    if not phrase:
        return text[:max_chars].strip()
    lower_text = text.lower()
    index = lower_text.find(phrase)
    if index == -1:
        return text[:max_chars].strip()
    start = max(0, index - 55)
    end = min(len(text), index + len(phrase) + 85)
    excerpt = text[start:end].strip()
    if start > 0:
        excerpt = f"...{excerpt}"
    if end < len(text):
        excerpt = f"{excerpt}..."
    return excerpt


def compute_score(
    *,
    rating: float | None,
    positive_total: float,
    negative_total: float,
    evidence_count: int,
) -> int:
    baseline = 48 if evidence_count == 0 else 52
    rating_adjustment = 0
    if rating is not None:
        rating_adjustment = max(-4, min(4, round((rating - 3.5) * 2)))

    raw_score = baseline + (positive_total * 14.0) - (negative_total * 12.0) + rating_adjustment
    return max(0, min(100, round(raw_score)))


def compute_confidence(evidence_count: int, specific_mentions: int) -> float:
    if evidence_count == 0:
        return 0.18
    confidence = 0.22 + (evidence_count * 0.1) + (specific_mentions * 0.06)
    return min(0.97, confidence)


def derive_verdict(score: int, confidence: float, evidence_count: int, severe_negative: bool) -> Verdict:
    if evidence_count == 0:
        return Verdict.USE_CAUTION
    if severe_negative or score <= 32:
        return Verdict.HIGH_RISK
    if score >= 72 and confidence >= 0.42:
        return Verdict.GOOD_FIT
    return Verdict.USE_CAUTION


def build_explanation(
    summary: PlaceScoreSummary,
    selected_allergens: list[AllergyTag],
    evidence: list[ReviewEvidence],
) -> str:
    allergen_names = ", ".join(ALLERGY_LABELS[allergen] for allergen in selected_allergens)
    if not evidence:
        return f"There is very little review evidence about {allergen_names} here, so Allernav keeps this rating cautious."

    positive = sum(1 for item in evidence if item.impact == ImpactDirection.POSITIVE)
    negative = sum(1 for item in evidence if item.impact == ImpactDirection.NEGATIVE)
    if summary.verdict == Verdict.GOOD_FIT:
        return f"Review evidence for {allergen_names} trends positive, with {positive} reassuring signals and {negative} risk notes."
    if summary.verdict == Verdict.HIGH_RISK:
        return f"Reviews include meaningful risk signals for {allergen_names}, including direct warnings or reaction reports."
    return f"Reviews for {allergen_names} are mixed or limited, so this place is better treated with caution."
