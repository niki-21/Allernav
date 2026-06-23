from __future__ import annotations

import json
import os
from typing import Any
from urllib import error, request

from .azure_search import detect_allergens_in_text, hybrid_search_menu
from .google_places import GooglePlacesClient
from .menu_ingestion import load_menu_source
from .models import (
    AllergyTag,
    HybridSearchRequest,
    HybridSearchResult,
    LatLng,
    NearbyPlaceSuggestion,
    NearbySuggestionRequest,
    NearbySuggestionResponse,
    PlaceListItem,
)

try:
    from langsmith import traceable
except ImportError:  # pragma: no cover - optional local dependency
    def traceable(*args: Any, **_kwargs: Any) -> Any:
        if args and callable(args[0]):
            return args[0]

        def decorator(func: Any) -> Any:
            return func

        return decorator


DEFAULT_CENTER = LatLng(lat=40.741895, lng=-73.989308)


@traceable(name="AllerNav Nearby Hybrid RAG", run_type="chain")
async def suggest_nearby_places_service(
    payload: NearbySuggestionRequest,
    client: GooglePlacesClient,
) -> NearbySuggestionResponse:
    center = payload.center or DEFAULT_CENTER
    candidates = collect_candidate_places(payload, center, client)
    suggestions = [
        build_place_suggestion(place, payload)
        for place in candidates[: payload.max_places]
    ]
    suggestions.sort(key=rank_suggestion, reverse=True)
    top_suggestions = suggestions[: min(3, len(suggestions))]
    evidence = [item for suggestion in top_suggestions for item in suggestion.evidence]
    missing_information = build_missing_information(top_suggestions)
    questions = build_recommended_questions(payload.allergens)
    answer = await generate_nearby_answer(payload, top_suggestions, evidence, missing_information, questions)

    return NearbySuggestionResponse(
        answer=answer,
        retrieval_mode="hybrid_keyword_semantic",
        places=top_suggestions,
        evidence=evidence,
        missing_information=missing_information,
        recommended_questions=questions,
    )


def collect_candidate_places(
    payload: NearbySuggestionRequest,
    center: LatLng,
    client: GooglePlacesClient,
) -> list[PlaceListItem]:
    if payload.candidate_place_ids:
        places: list[PlaceListItem] = []
        for place_id in payload.candidate_place_ids[: payload.max_places]:
            try:
                details = client.get_place_details(place_id)
            except Exception:  # noqa: BLE001 - one bad place should not fail nearby RAG
                continue
            places.append(place_from_details(details))
        return places

    query = restaurant_search_query(payload.question, payload.query)
    return client.search_places(query, center, max_results=payload.max_places)


def restaurant_search_query(question: str, fallback: str = "") -> str:
    text = f"{question} {fallback}".lower()
    cuisine_terms = [
        "bagel",
        "bakery",
        "breakfast",
        "brunch",
        "burger",
        "cafe",
        "chinese",
        "deli",
        "dinner",
        "gluten free",
        "indian",
        "italian",
        "japanese",
        "korean",
        "lunch",
        "mediterranean",
        "mexican",
        "pizza",
        "ramen",
        "restaurant",
        "salad",
        "sushi",
        "thai",
        "vegan",
        "vegetarian",
    ]
    matched = [term for term in cuisine_terms if term in text]
    if not matched:
        return "restaurants"
    if "restaurant" in matched or "restaurants" in text:
        return "restaurants"
    return f"{matched[0]} restaurants"


def place_from_details(details: dict[str, Any]) -> PlaceListItem:
    location = details.get("location") or {}
    return PlaceListItem(
        id=str(details["id"]),
        name=str(details.get("name") or "Unknown place"),
        address=details.get("address"),
        location=LatLng(
            lat=float(location.get("lat", 0.0)),
            lng=float(location.get("lng", 0.0)),
        ),
        rating=details.get("rating"),
        user_rating_count=details.get("user_rating_count"),
        primary_type=details.get("primary_type"),
    )


def build_place_suggestion(place: PlaceListItem, payload: NearbySuggestionRequest) -> NearbyPlaceSuggestion:
    source = load_menu_source(place.id)
    menu_item_count = sum(len(section.items) for section in source.sections) if source else 0
    matched_allergen_items = 0
    if source:
        for section in source.sections:
            for item in section.items:
                matched = detect_allergens_in_text(f"{item.name} {item.description or ''}")
                if any(allergen in payload.allergens for allergen in matched):
                    matched_allergen_items += 1

    evidence = hybrid_search_menu(
        HybridSearchRequest(
            query=payload.question,
            restaurant_id=place.id,
            allergens=payload.allergens,
            top=payload.top_evidence,
        )
    ).results
    confidence = suggestion_confidence(menu_item_count, len(evidence), matched_allergen_items)
    return NearbyPlaceSuggestion(
        place=place,
        confidence=confidence,
        menu_item_count=menu_item_count,
        matched_allergen_items=matched_allergen_items,
        evidence=evidence,
        risk_note=build_risk_note(menu_item_count, matched_allergen_items, evidence),
    )


def suggestion_confidence(menu_item_count: int, evidence_count: int, matched_allergen_items: int) -> float:
    if menu_item_count == 0:
        return 0.18
    confidence = 0.36 + min(menu_item_count, 20) * 0.018 + evidence_count * 0.06 - matched_allergen_items * 0.025
    return round(max(0.18, min(0.82, confidence)), 2)


def build_risk_note(
    menu_item_count: int,
    matched_allergen_items: int,
    evidence: list[HybridSearchResult],
) -> str:
    if menu_item_count == 0:
        return "No stored official menu evidence is available yet, so this place should not be ranked as lower risk."
    if matched_allergen_items:
        return (
            f"Menu evidence includes {matched_allergen_items} item"
            f"{'s' if matched_allergen_items != 1 else ''} with selected-allergen terms; treat this as a verification target."
        )
    if evidence:
        return "Stored menu evidence was retrieved, but ingredients and cross-contact handling still need staff verification."
    return "Stored menu exists, but the current question did not retrieve enough source-backed evidence."


def rank_suggestion(suggestion: NearbyPlaceSuggestion) -> float:
    rating = suggestion.place.rating or 0
    return (
        suggestion.confidence * 100
        + suggestion.menu_item_count * 1.2
        + rating * 3
        - suggestion.matched_allergen_items * 8
        + len(suggestion.evidence) * 5
    )


def build_missing_information(suggestions: list[NearbyPlaceSuggestion]) -> list[str]:
    missing: list[str] = []
    if not suggestions:
        return ["No nearby candidates were available for retrieval."]
    if any(item.menu_item_count == 0 for item in suggestions):
        missing.append("Some nearby places do not have stored official menu evidence yet.")
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
    llm_answer = generate_gemini_answer(payload, suggestions, evidence, missing_information, questions)
    if llm_answer:
        return llm_answer
    return deterministic_answer(payload, suggestions, missing_information, questions)


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
    prompt = {
        "task": "Suggest nearby restaurants to evaluate for allergy-aware dining decision support.",
        "rules": [
            "Never claim a place or dish is safe.",
            "Use cautious language: lower-risk candidate, verify, ask staff, insufficient evidence.",
            "Use menu evidence as stronger evidence than reviews.",
            "Cite evidence ids like [E1] when discussing menu facts.",
            "Do not invent menu items, ingredients, policies, or reviews.",
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
        "output": "One short paragraph plus 2-3 concise bullets. No JSON.",
    }
    req = request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        method="POST",
        data=json.dumps(
            {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": (
                                    "You are AllerNav, an evidence-backed dining decision-support assistant. "
                                    "Answer cautiously and cite only provided evidence.\n\n"
                                    + json.dumps(prompt)
                                )
                            }
                        ],
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
    blocked = ["definitely safe", "completely safe", "guaranteed safe", "is safe to eat", "are safe to eat"]
    cleaned = answer.strip()
    lowered = cleaned.lower()
    if any(phrase in lowered for phrase in blocked):
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
            "No ranked restaurant candidates yet. Try a cuisine or move the map."
        )

    lines = ["Restaurant candidates ranked from available menu and place evidence:"]
    for suggestion in suggestions:
        lines.append(f"- {suggestion.place.name}: {round(suggestion.confidence * 100)}/100")
    return "\n".join(lines)
