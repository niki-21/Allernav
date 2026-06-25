from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from hashlib import sha1
from typing import Any
from urllib import error, parse, request
from .azure_openai_embeddings import AzureOpenAIEmbeddingClient, configured_embeddings

from .menu_ingestion import load_menu_record, load_menu_source
from .models import (
    AllergyTag,
    HybridSearchRequest,
    HybridSearchResponse,
    HybridSearchResult,
    MenuItem,
    MenuSource,
    SearchIndexResponse,
    SourceType,
)
from .risk_engine import ALLERGEN_TERMS, term_matches


def configured_search() -> bool:
    return bool(
        os.getenv("AZURE_SEARCH_ENDPOINT")
        and os.getenv("AZURE_SEARCH_API_KEY")
        and os.getenv("AZURE_SEARCH_INDEX_NAME")
    )


def search_api_version() -> str:
    return os.getenv("AZURE_SEARCH_API_VERSION", "2026-04-01")


def build_index_documents(
    *,
    restaurant_id: str,
    restaurant_name: str | None,
    source: MenuSource,
    location: str | None = None,
) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for section in source.sections:
        for item in section.items:
            raw_text = item_text(item)
            matched_allergens = detect_allergens_in_text(raw_text)
            embedding = AzureOpenAIEmbeddingClient().embed_text(raw_text) if configured_embeddings() else []

            documents.append(
                {
                    "id": document_id(restaurant_id, source, section.title, item.name),
                    "restaurant_id": restaurant_id,
                    "restaurant_name": restaurant_name,
                    "location": location,
                    "dish_name": item.name,
                    "menu_section": section.title,
                    "ingredients": item.description or "",
                    "allergens": [allergen.value for allergen in matched_allergens],
                    "source_type": source.source_type.value,
                    "source_url": source.source_url,
                    "source_timestamp": source.source_timestamp,
                    "confidence": freshness_adjusted_confidence(
                        source.source_timestamp,
                        source.extraction_confidence if source.extraction_confidence is not None else source.reliability,
                    ),
                    "raw_text": raw_text,
                    "embedding": embedding,
                }
            )
    return documents


def build_hybrid_query(payload: HybridSearchRequest) -> dict[str, Any]:
    body: dict[str, Any] = {
        "search": build_keyword_query(payload.query, payload.allergens),
        "top": payload.top,
    }

    filters = []
    if payload.restaurant_id:
        filters.append(f"restaurant_id eq '{escape_filter_value(payload.restaurant_id)}'")
    if payload.source_types:
        source_filter = " or ".join(
            f"source_type eq '{escape_filter_value(source_type.value)}'" for source_type in payload.source_types
        )
        filters.append(f"({source_filter})")
    if filters:
        body["filter"] = " and ".join(filters)

    query_vector = payload.vector
    if query_vector is None and configured_embeddings() and payload.query.strip():
        query_vector = AzureOpenAIEmbeddingClient().embed_text(payload.query)

    if query_vector:
        body["vectorQueries"] = [
            {
                "kind": "vector",
                "vector": query_vector,
                "fields": "embedding",
                "k": payload.top,
            }
        ]

    return body

def build_keyword_query(query: str, allergens: list[AllergyTag]) -> str:
    allergen_terms = [term for allergen in allergens for term in ALLERGEN_TERMS[allergen]]
    pieces = [query.strip(), *allergen_terms]
    return " ".join(piece for piece in pieces if piece)


def index_restaurant_menu(restaurant_id: str) -> SearchIndexResponse:
    record = load_menu_record(restaurant_id)
    if not record:
        return SearchIndexResponse(restaurant_id=restaurant_id, indexed_documents=0, status="missing_menu")
    restaurant_name, source = record
    documents = build_index_documents(
        restaurant_id=restaurant_id,
        restaurant_name=restaurant_name,
        source=source,
    )
    if not documents:
        return SearchIndexResponse(restaurant_id=restaurant_id, indexed_documents=0, status="empty_menu")
    if not configured_search():
        return SearchIndexResponse(restaurant_id=restaurant_id, indexed_documents=len(documents), status="skipped_unconfigured")

    AzureSearchClient().upload_documents(documents)
    return SearchIndexResponse(restaurant_id=restaurant_id, indexed_documents=len(documents), status="indexed")


def hybrid_search_menu(payload: HybridSearchRequest) -> HybridSearchResponse:
    if configured_search():
        return AzureSearchClient().hybrid_search(payload)
    return local_hybrid_search(payload)


def local_hybrid_search(payload: HybridSearchRequest) -> HybridSearchResponse:
    if not payload.restaurant_id:
        return HybridSearchResponse(query=payload.query, results=[])
    source = load_menu_source(payload.restaurant_id)
    if not source:
        return HybridSearchResponse(query=payload.query, results=[])

    documents = build_index_documents(
        restaurant_id=payload.restaurant_id,
        restaurant_name=None,
        source=source,
    )
    scored_results: list[tuple[float, HybridSearchResult]] = []
    keyword_query = build_keyword_query(payload.query, payload.allergens).lower()
    query_terms = [term for term in keyword_query.split() if len(term) >= 3]
    for document in documents:
        text = str(document["raw_text"]).lower()
        matched_allergens = [allergen for allergen in detect_allergens_in_text(text) if not payload.allergens or allergen in payload.allergens]
        keyword_match = any(term in text for term in query_terms) or bool(matched_allergens)
        semantic_score = local_semantic_score(payload.query, text)
        if payload.vector and not keyword_match:
            retrieval_mode = "vector"
        elif keyword_match and semantic_score > 0:
            retrieval_mode = "hybrid"
        elif keyword_match:
            retrieval_mode = "keyword"
        elif semantic_score > 0:
            retrieval_mode = "semantic"
        else:
            retrieval_mode = ""
        if not retrieval_mode:
            continue
        score = (10 if keyword_match else 0) + semantic_score + len(matched_allergens) * 5
        scored_results.append((score, document_to_result(document, matched_allergens, retrieval_mode)))
    scored_results.sort(key=lambda item: item[0], reverse=True)
    return HybridSearchResponse(query=payload.query, results=[result for _, result in scored_results[: payload.top]])


class AzureSearchClient:
    def __init__(
        self,
        *,
        endpoint: str | None = None,
        api_key: str | None = None,
        index_name: str | None = None,
    ) -> None:
        self.endpoint = (endpoint or os.getenv("AZURE_SEARCH_ENDPOINT", "")).rstrip("/")
        self.api_key = api_key or os.getenv("AZURE_SEARCH_API_KEY", "")
        self.index_name = index_name or os.getenv("AZURE_SEARCH_INDEX_NAME", "")

    def upload_documents(self, documents: list[dict[str, Any]]) -> None:
        url = f"{self.endpoint}/indexes/{self.index_name}/docs/index?api-version={search_api_version()}"
        payload = {"value": [document | {"@search.action": "upload"} for document in documents]}
        self._request_json(url, "POST", payload)

    def hybrid_search(self, payload: HybridSearchRequest) -> HybridSearchResponse:
        url = f"{self.endpoint}/indexes/{self.index_name}/docs/search?api-version={search_api_version()}"
        response = self._request_json(url, "POST", build_hybrid_query(payload))
        values = response.get("value") if isinstance(response, dict) else []
        results = [
            document_to_result(
                document,
                [allergen for allergen in detect_allergens_in_text(str(document.get("raw_text", ""))) if not payload.allergens or allergen in payload.allergens],
                "hybrid" if payload.vector else "keyword",
            )
            for document in values
            if isinstance(document, dict)
        ]
        return HybridSearchResponse(query=payload.query, results=results)

    def _request_json(self, url: str, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        req = request.Request(url, data=json.dumps(payload).encode("utf-8"), method=method)
        req.add_header("api-key", self.api_key)
        req.add_header("Content-Type", "application/json")
        try:
            with request.urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode("utf-8", errors="ignore") or "{}")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Azure AI Search request failed: {exc.code} {detail}") from exc
        except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("Azure AI Search request failed.") from exc

def document_to_result(document: dict[str, Any], matched_allergens: list[AllergyTag], retrieval_mode: str) -> HybridSearchResult:
    try:
        source_type = SourceType(str(document.get("source_type") or SourceType.UNKNOWN.value))
    except ValueError:
        source_type = SourceType.UNKNOWN
    return HybridSearchResult(
        id=str(document.get("id")),
        restaurant_id=str(document.get("restaurant_id")),
        restaurant_name=optional_string(document.get("restaurant_name")),
        dish_name=optional_string(document.get("dish_name")),
        menu_section=optional_string(document.get("menu_section")),
        source_type=source_type,
        source_url=optional_string(document.get("source_url")),
        source_timestamp=optional_string(document.get("source_timestamp")),
        confidence=float(document.get("confidence") or 0.5),
        raw_text=str(document.get("raw_text") or ""),
        matched_allergens=matched_allergens,
        retrieval_mode=retrieval_mode,
        can_support_low_risk=retrieval_mode not in {"vector", "semantic"} and source_type != SourceType.REVIEW,
    )


def local_semantic_score(query: str, text: str) -> float:
    lowered_query = query.lower()
    intent_terms: list[str] = []
    if any(term in lowered_query for term in ["lower risk", "safer", "suggest", "recommend", "option", "evaluate"]):
        intent_terms.extend(["grilled", "roasted", "baked", "rice", "salad", "vegetable", "veggie", "bowl", "plain"])
    if any(term in lowered_query for term in ["breakfast", "brunch"]):
        intent_terms.extend(["oatmeal", "fruit", "toast", "egg", "coffee"])
    if any(term in lowered_query for term in ["dinner", "lunch"]):
        intent_terms.extend(["chicken", "rice", "salad", "steak", "vegetable"])
    return float(sum(1 for term in intent_terms if term_matches(text, term)))


def detect_allergens_in_text(text: str) -> list[AllergyTag]:
    lowered = text.lower()
    return [
        allergen
        for allergen, terms in ALLERGEN_TERMS.items()
        if any(term_matches(lowered, term) for term in terms)
    ]


def freshness_adjusted_confidence(source_timestamp: str | None, base_confidence: float | None) -> float:
    confidence = max(0.0, min(1.0, base_confidence if base_confidence is not None else 0.5))
    if not source_timestamp:
        return round(confidence * 0.9, 2)
    try:
        timestamp = datetime.fromisoformat(source_timestamp.replace("Z", "+00:00"))
    except ValueError:
        return round(confidence * 0.9, 2)
    age_days = (datetime.now(UTC) - timestamp.astimezone(UTC)).days
    if age_days > 365:
        confidence *= 0.7
    elif age_days > 180:
        confidence *= 0.85
    return round(confidence, 2)


def item_text(item: MenuItem) -> str:
    return f"{item.name}: {item.description}" if item.description else item.name


def document_id(restaurant_id: str, source: MenuSource, section_title: str, dish_name: str) -> str:
    digest = sha1(f"{restaurant_id}:{source.source_url}:{section_title}:{dish_name}".encode("utf-8")).hexdigest()
    return digest[:24]


def escape_filter_value(value: str) -> str:
    return value.replace("'", "''")


def optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
