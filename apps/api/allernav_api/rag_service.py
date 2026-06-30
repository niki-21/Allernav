from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any
from urllib import error, request

from .azure_search import hybrid_search_menu
from .langchain_tracing import (
    ainvoke_traced_runnable,
    invoke_traced_runnable,
    langchain_run_config,
    update_current_trace_metadata,
)
from .menu_ingestion import load_menu_source
from .models import (
    AllergyTag,
    HybridSearchRequest,
    HybridSearchResult,
    MenuSource,
    NearbyPlaceSuggestion,
    NearbySuggestionRequest,
    NearbySuggestionResponse,
    PlaceListItem,
)
from .restaurant_scoring import score_restaurant_menu

try:
    from langsmith import traceable
except ImportError:  # pragma: no cover - optional local dependency
    def traceable(*args: Any, **_kwargs: Any) -> Any:
        if args and callable(args[0]):
            return args[0]

        def decorator(func: Any) -> Any:
            return func

        return decorator


@traceable(name="AllerNav Nearby Hybrid RAG", run_type="chain")
async def suggest_nearby_places_service(
    payload: NearbySuggestionRequest,
) -> NearbySuggestionResponse:
    candidates = payload.candidate_places[: payload.max_places]
    candidate_sources = [(place, load_menu_source(place.id)) for place in candidates]
    suggestions = list(
        await asyncio.gather(
            *(
                asyncio.to_thread(build_place_suggestion, place, payload, source)
                for place, source in candidate_sources
            )
        )
    )
    if payload.allow_background_scan:
        suggestions = await start_background_scans(suggestions)
    suggestions.sort(key=suggestion_rank_key, reverse=True)

    scanned = [suggestion for suggestion in suggestions if suggestion.evidence_status == "scanned"]
    scan_needed = [suggestion for suggestion in suggestions if suggestion.evidence_status != "scanned"]
    evidence = [item for suggestion in scanned for item in suggestion.evidence]
    missing_information = build_missing_information(suggestions)
    questions = build_recommended_questions(payload.allergens)
    answer = build_nearby_summary(len(candidates), scanned, scan_needed)
    retrieval_mode = "hybrid_keyword_semantic" if scanned else "scanned_menu_evidence_needed"
    trace_nearby_result(payload, suggestions, retrieval_mode)

    return NearbySuggestionResponse(
        answer=answer,
        retrieval_mode=retrieval_mode,
        places=suggestions,
        evidence=evidence,
        missing_information=missing_information,
        recommended_questions=questions,
        scan_needed_places=[suggestion.place for suggestion in scan_needed],
    )


def build_place_suggestion(
    place: PlaceListItem,
    payload: NearbySuggestionRequest,
    source: MenuSource | None,
) -> NearbyPlaceSuggestion:
    fit = score_restaurant_menu(source, payload.allergens)

    evidence: list[HybridSearchResult] = []
    if source and fit.menu_item_count > 0:
        search_request = HybridSearchRequest(
            query=payload.question,
            restaurant_id=place.id,
            allergens=payload.allergens,
            top=payload.top_evidence,
        )
        search_response = invoke_traced_runnable(
            name="AllerNav Azure Search Retriever",
            value=search_request,
            func=hybrid_search_menu,
            metadata={
                "restaurant_id": place.id,
                "source_url": source.source_url,
                "item_count": fit.menu_item_count,
                "retrieval_mode": "hybrid",
                "allergens": [allergen.value for allergen in payload.allergens],
            },
        )
        evidence = search_response.results
    update_current_trace_metadata(
        restaurant_id=place.id,
        item_count=fit.menu_item_count,
        retrieval_mode=(evidence[0].retrieval_mode if evidence else "hybrid_no_results"),
        allergens=[allergen.value for allergen in payload.allergens],
    )
    return NearbyPlaceSuggestion(
        place=place,
        confidence=round(fit.score / 100, 2),
        evidence_status="scanned" if fit.menu_item_count > 0 else "scan_needed",
        restaurant_fit_score=fit.score,
        restaurant_fit_label=fit.label,
        menu_item_count=fit.menu_item_count,
        matched_allergen_items=fit.avoid_count,
        avoid_count=fit.avoid_count,
        needs_check_count=fit.needs_check_count,
        possible_lower_risk_count=fit.possible_lower_risk_count,
        insufficient_info_count=fit.insufficient_info_count,
        evidence_quality=fit.evidence_quality,
        evidence_count=len(evidence),
        evidence=evidence,
        risk_note=fit.reason,
        reason=fit.reason,
        next_action=fit.next_action,
    )


def suggestion_rank_key(suggestion: NearbyPlaceSuggestion) -> tuple[int, int]:
    return (1 if suggestion.evidence_status == "scanned" else 0, suggestion.restaurant_fit_score)


async def start_background_scans(
    suggestions: list[NearbyPlaceSuggestion],
) -> list[NearbyPlaceSuggestion]:
    eligible = [
        suggestion
        for suggestion in suggestions
        if suggestion.evidence_status == "scan_needed" and suggestion.place.website_url
    ][:2]
    if not eligible:
        return suggestions

    from .service import create_menu_refresh_job

    jobs = await asyncio.gather(
        *(
            create_menu_refresh_job(
                suggestion.place.id,
                restaurant_name=suggestion.place.name,
                website_url=suggestion.place.website_url,
                allow_local_fallback=False,
            )
            for suggestion in eligible
        )
    )
    updates = {suggestion.place.id: job for suggestion, job in zip(eligible, jobs, strict=True)}
    return [apply_scan_job(suggestion, updates.get(suggestion.place.id)) for suggestion in suggestions]


def apply_scan_job(suggestion: NearbyPlaceSuggestion, job: Any | None) -> NearbyPlaceSuggestion:
    if job is None:
        return suggestion
    if job.status == "failed":
        return suggestion.model_copy(
            update={
                "evidence_status": "scan_failed",
                "scan_job_id": job.id,
                "reason": "The background menu scan could not be started.",
                "risk_note": "The background menu scan could not be started.",
                "next_action": "Open the restaurant and retry its menu scan.",
            }
        )
    return suggestion.model_copy(
        update={
            "evidence_status": "scan_running",
            "scan_job_id": job.id,
            "reason": "A background menu scan is running.",
            "risk_note": "A background menu scan is running.",
            "next_action": "Check again after the menu scan finishes.",
        }
    )


def build_nearby_summary(
    candidate_count: int,
    scanned: list[NearbyPlaceSuggestion],
    scan_needed: list[NearbyPlaceSuggestion],
) -> str:
    if candidate_count == 0:
        return "I could not find nearby candidates in the current map area."
    place_word = "place" if candidate_count == 1 else "places"
    running_count = sum(item.evidence_status == "scan_running" for item in scan_needed)
    if not scanned:
        suffix = f" Background scans are running for {running_count}." if running_count else ""
        need_phrase = "it needs a menu scan" if candidate_count == 1 else "they need menu scans"
        return f"I found {candidate_count} nearby {place_word}, but {need_phrase} before comparison.{suffix}"
    if len(scanned) == 1:
        other_count = max(0, candidate_count - 1)
        if other_count == 0:
            return f"I found 1 nearby place and ranked {scanned[0].place.name} using scanned menu evidence."
        other_word = "place" if other_count == 1 else "places"
        return (
            f"I found {candidate_count} nearby {place_word}. Only {scanned[0].place.name} has scanned menu evidence "
            f"right now, so I can rank it but the other {other_count} {other_word} need menu scans before comparison."
        )
    return (
        f"I found {candidate_count} nearby {place_word} and ranked {len(scanned)} with scanned menu evidence; "
        f"{len(scan_needed)} still need menu scans before comparison."
    )


def trace_nearby_result(
    payload: NearbySuggestionRequest,
    suggestions: list[NearbyPlaceSuggestion],
    retrieval_mode: str,
) -> None:
    scanned = [item for item in suggestions if item.evidence_status == "scanned"]
    top = scanned[0] if scanned else (suggestions[0] if suggestions else None)
    update_current_trace_metadata(
        candidate_count=len(suggestions),
        scanned_candidate_count=len(scanned),
        scan_needed_count=len(suggestions) - len(scanned),
        selected_allergens=[allergen.value for allergen in payload.allergens],
        top_ranked_place=top.place.name if top else None,
        restaurant_fit_score=top.restaurant_fit_score if top else None,
        retrieval_mode=retrieval_mode,
        allow_background_scan=payload.allow_background_scan,
        safety_gate="verify_or_abstain",
    )


def build_missing_information(suggestions: list[NearbyPlaceSuggestion]) -> list[str]:
    missing: list[str] = []
    if not suggestions:
        return ["No nearby candidates were available for retrieval."]
    if any(item.menu_item_count == 0 for item in suggestions):
        missing.append("Some nearby places do not have scanned menu evidence yet.")
    if any(item.menu_item_count > 0 for item in suggestions):
        missing.append("Menus rarely confirm cross-contact controls, shared fryer use, or ingredient substitutions.")
    return missing


def build_recommended_questions(allergens: list[AllergyTag]) -> list[str]:
    allergen_text = ", ".join(allergen.value.replace("_", " ") for allergen in allergens) or "my allergens"
    return [
        f"Can you confirm whether this dish contains {allergen_text} directly or through sauces, marinades, or garnish?",
        "Is it prepared on shared surfaces, grills, fryers, or utensils?",
        "Can staff check the current ingredient label or kitchen prep notes before I order?",
    ]


async def generate_nearby_answer(
    payload: NearbySuggestionRequest,
    suggestions: list[NearbyPlaceSuggestion],
    evidence: list[HybridSearchResult],
    missing_information: list[str],
    questions: list[str],
) -> str:
    metadata = explanation_trace_metadata(payload, suggestions, evidence)

    async def explain(_input: dict[str, str]) -> str:
        llm_answer = await generate_azure_openai_answer(
            payload,
            suggestions,
            evidence,
            missing_information,
            questions,
            metadata=metadata,
        )
        if not llm_answer:
            llm_answer = generate_gemini_answer(payload, suggestions, evidence, missing_information, questions)
        answer = llm_answer or deterministic_answer(payload, suggestions, missing_information, questions)
        update_current_trace_metadata(
            retrieval_mode="hybrid_keyword_semantic",
            safety_gate="verify_or_abstain",
            item_count=sum(suggestion.menu_item_count for suggestion in suggestions),
        )
        return answer

    return await ainvoke_traced_runnable(
        name="AllerNav RAG Explanation",
        value={"question": payload.question},
        func=explain,
        metadata=metadata,
    )


def azure_openai_chat_configured() -> bool:
    return all(
        os.getenv(name, "").strip()
        for name in (
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_CHAT_DEPLOYMENT",
            "AZURE_OPENAI_CHAT_API_VERSION",
        )
    )


def explanation_trace_metadata(
    payload: NearbySuggestionRequest,
    suggestions: list[NearbyPlaceSuggestion],
    evidence: list[HybridSearchResult],
) -> dict[str, Any]:
    return {
        "restaurant_id": suggestions[0].place.id if len(suggestions) == 1 else None,
        "source_url": evidence[0].source_url if evidence else None,
        "item_count": sum(suggestion.menu_item_count for suggestion in suggestions),
        "retrieval_mode": "hybrid_keyword_semantic",
        "allergens": [allergen.value for allergen in payload.allergens],
        "safety_gate": "verify_or_abstain",
    }


async def generate_azure_openai_answer(
    payload: NearbySuggestionRequest,
    suggestions: list[NearbyPlaceSuggestion],
    evidence: list[HybridSearchResult],
    missing_information: list[str],
    questions: list[str],
    *,
    metadata: dict[str, Any],
) -> str | None:
    if not azure_openai_chat_configured() or not suggestions:
        return None
    try:
        from langchain_openai import AzureChatOpenAI

        model = AzureChatOpenAI(
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", "").strip(),
            api_key=os.getenv("AZURE_OPENAI_API_KEY", "").strip(),
            azure_deployment=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "").strip(),
            api_version=os.getenv("AZURE_OPENAI_CHAT_API_VERSION", "").strip(),
            temperature=0.2,
            max_retries=1,
            timeout=14,
        )
        response = await model.ainvoke(
            explanation_messages(payload, suggestions, evidence, missing_information, questions),
            config=langchain_run_config(
                name="AllerNav Azure OpenAI RAG Explanation",
                tags=["allernav", "rag", "azure-openai"],
                metadata=metadata,
            ),
        )
    except Exception:  # noqa: BLE001 - provider failure must preserve the fallback chain
        return None
    return clean_llm_answer(extract_langchain_text(response))


@traceable(name="Gemini Nearby RAG Explanation", run_type="llm")
def generate_gemini_answer(
    payload: NearbySuggestionRequest,
    suggestions: list[NearbyPlaceSuggestion],
    evidence: list[HybridSearchResult],
    missing_information: list[str],
    questions: list[str],
) -> str | None:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or not suggestions:
        return None

    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip() or "gemini-3.5-flash"
    messages = explanation_messages(payload, suggestions, evidence, missing_information, questions)
    req = request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        method="POST",
        data=json.dumps(
            {
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": f"{messages[0][1]}\n\n{messages[1][1]}"}],
                    }
                ],
                "generationConfig": {"temperature": 0.2},
            }
        ).encode("utf-8"),
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("x-goog-api-key", api_key)
    try:
        with request.urlopen(req, timeout=14) as response:
            payload_json = json.loads(response.read().decode("utf-8", errors="ignore") or "{}")
    except (error.HTTPError, error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return None
    return clean_llm_answer(extract_gemini_text(payload_json))


def explanation_prompt(
    payload: NearbySuggestionRequest,
    suggestions: list[NearbyPlaceSuggestion],
    evidence: list[HybridSearchResult],
    missing_information: list[str],
    questions: list[str],
) -> dict[str, Any]:
    return {
        "task": "Suggest nearby restaurants to evaluate for allergy-aware dining decision support.",
        "rules": [
            "Never use the word safe or claim that a place or dish has no allergy risk.",
            "Use cautious language: possible lower-risk, needs verification, ask staff, insufficient evidence.",
            "Use menu evidence as stronger evidence than reviews.",
            "Cite evidence ids like [E1] when discussing menu facts.",
            "Do not invent menu items, ingredients, policies, or reviews.",
            "If no menu evidence was retrieved, say menu refresh or OCR is needed before ranking candidates.",
            "Do not list internal confidence percentages or item counts unless they directly explain an evidence gap.",
        ],
        "question": payload.question,
        "selected_allergens": [allergen.value for allergen in payload.allergens],
        "places": [
            {
                "name": suggestion.place.name,
                "rating": suggestion.place.rating,
                "menu_item_count": suggestion.menu_item_count,
                "confidence": suggestion.confidence,
                "risk_note": suggestion.risk_note,
                "evidence_ids": [result.id for result in suggestion.evidence],
            }
            for suggestion in suggestions
        ],
        "evidence": [
            {
                "id": f"E{index + 1}",
                "document_id": result.id,
                "restaurant_name": result.restaurant_name,
                "dish_name": result.dish_name,
                "source_type": result.source_type.value,
                "text": result.raw_text,
                "matched_allergens": [allergen.value for allergen in result.matched_allergens],
            }
            for index, result in enumerate(evidence[:8])
        ],
        "missing_information": missing_information,
        "recommended_questions": questions,
        "output": "Maximum 80 words. One short paragraph and, only when useful, up to 2 concise bullets. No JSON.",
    }


def explanation_messages(
    payload: NearbySuggestionRequest,
    suggestions: list[NearbyPlaceSuggestion],
    evidence: list[HybridSearchResult],
    missing_information: list[str],
    questions: list[str],
) -> list[tuple[str, str]]:
    prompt = explanation_prompt(payload, suggestions, evidence, missing_information, questions)
    return [
        (
            "system",
            "You are AllerNav, an evidence-backed dining decision-support assistant. "
            "Follow the supplied safety rules and cite only supplied evidence ids.",
        ),
        ("human", json.dumps(prompt)),
    ]


def extract_langchain_text(response: Any) -> str | None:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content.strip() or None
    if isinstance(content, list):
        parts = [part.get("text", "") for part in content if isinstance(part, dict)]
        joined = "".join(parts).strip()
        return joined or None
    return None


def extract_gemini_text(payload: dict[str, Any]) -> str | None:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        return None
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list):
            continue
        text = "".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()
        if text:
            return text
    return None


def clean_llm_answer(answer: str | None) -> str | None:
    if not answer:
        return None
    cleaned = answer.strip()
    if re.search(r"\bsafe\b", cleaned, flags=re.IGNORECASE):
        return None
    return cleaned


def deterministic_answer(
    payload: NearbySuggestionRequest,
    suggestions: list[NearbyPlaceSuggestion],
    missing_information: list[str],
    questions: list[str],
) -> str:
    if not suggestions:
        return (
            "I could not retrieve enough nearby place or menu evidence to suggest candidates. "
            "Try searching a specific cuisine or opening a place so AllerNav can capture menu evidence."
        )

    allergen_text = ", ".join(allergen.value.replace("_", " ") for allergen in payload.allergens) or "your allergens"
    place_names = ", ".join(suggestion.place.name for suggestion in suggestions[:3])
    has_menu_evidence = any(suggestion.menu_item_count > 0 or suggestion.evidence for suggestion in suggestions)
    if not has_menu_evidence:
        return (
            f"I found nearby {allergen_text} verification candidates, but none have stored menu evidence yet: "
            f"{place_names}. Open a place and refresh its menu or OCR source before treating it as a useful allergy lead. "
            f"Ask staff: {questions[0]}"
        )

    lines = [f"For {allergen_text}, use these as verification leads, not verified choices:"]
    for suggestion in suggestions[:3]:
        evidence_count = len(suggestion.evidence)
        if evidence_count > 0:
            evidence_text = f"{evidence_count} cited menu fragment{'s' if evidence_count != 1 else ''}"
        elif suggestion.menu_item_count > 0:
            evidence_text = "stored menu items, but weak retrieval for this question"
        else:
            evidence_text = "no stored menu evidence yet"
        lines.append(f"- {suggestion.place.name}: {evidence_text}. {suggestion.risk_note}")
    if missing_information:
        lines.append("Gap: " + missing_information[0])
    lines.append("Ask staff: " + questions[0])
    return "\n".join(lines)
