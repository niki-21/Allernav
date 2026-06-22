from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

from .agent_graph import run_dining_safety_graph
from .azure_search import hybrid_search_menu, index_restaurant_menu
from .google_places import GooglePlacesClient
from .menu_ingestion import ingest_menu_from_website, load_menu_source, load_place_menu
from .models import (
    AllergyProfile,
    AllergyTag,
    HybridSearchRequest,
    HybridSearchResponse,
    AskRestaurantRequest,
    AskRestaurantResponse,
    LatLng,
    MenuRefreshJob,
    PlaceDetailsResponse,
    PlaceMenu,
    PlaceReviewSnippet,
    RestaurantContext,
    ReviewRefreshJob,
    ReviewSourceSummary,
    SearchRequest,
    SearchResponse,
    SearchIndexResponse,
    UserProfileResponse,
)
from .apify_reviews import fetch_apify_reviews, load_cached_reviews
from .scoring import analyze_place


DEFAULT_CENTER = LatLng(lat=40.741895, lng=-73.989308)
MENU_REFRESH_JOBS: dict[str, MenuRefreshJob] = {}
REVIEW_REFRESH_JOBS: dict[str, ReviewRefreshJob] = {}
ASK_REQUESTS: dict[str, AskRestaurantResponse] = {}
PROFILE = UserProfileResponse()


async def search_places_service(
    payload: SearchRequest,
    client: GooglePlacesClient,
) -> SearchResponse:
    center = payload.center or DEFAULT_CENTER
    places = client.search_places(payload.query, center, max_results=payload.max_results)
    return SearchResponse(
        query=payload.query,
        center=center,
        allergens=payload.allergens,
        places=places,
    )


async def get_place_details_service(
    place_id: str,
    allergens: list[AllergyTag],
    client: GooglePlacesClient,
) -> PlaceDetailsResponse:
    selected_allergens = allergens or [AllergyTag.PEANUT]
    place = client.get_place_details(place_id)
    google_review_count = len(place.get("reviews", []))
    apify_reviews = load_cached_reviews(place["id"])
    if apify_reviews:
        place = {
            **place,
            "reviews": merge_review_sources(place.get("reviews", []), apify_reviews),
        }
    summary, evidence, explanation = analyze_place(place, selected_allergens)
    menu_source = load_menu_source(place["id"])
    menu = load_place_menu(place["id"]) if menu_source else None
    if not summary.fit_score:
        summary.fit_score = summary.score
    if summary.fit_verdict is None:
        summary.fit_verdict = summary.verdict
    if not summary.evidence_confidence:
        summary.evidence_confidence = summary.confidence
    summary.meaningful_evidence = summary.evidence_count > 0
    summary.evidence_status = "meaningful" if summary.meaningful_evidence else "limited"
    summary.evidence_summary = "Allergy-specific evidence found" if summary.meaningful_evidence else "Not enough allergy-specific evidence"
    agent_recommendation = run_dining_safety_graph(
        profile=AllergyProfile(allergens=selected_allergens),
        restaurant_id=place["id"],
        restaurant_name=place["name"],
        context=RestaurantContext(
            restaurant_id=place["id"],
            restaurant_name=place["name"],
            website_url=place.get("website_uri") if menu_source else None,
            menu_sources=[menu_source] if menu_source else [],
        ),
    )

    return PlaceDetailsResponse(
        id=place["id"],
        name=place["name"],
        address=place.get("address"),
        location=LatLng(**place["location"]),
        rating=place.get("rating"),
        user_rating_count=place.get("user_rating_count"),
        primary_type=place.get("primary_type"),
        website_uri=place.get("website_uri"),
        editorial_summary=place.get("editorial_summary"),
        national_phone_number=place.get("national_phone_number"),
        international_phone_number=place.get("international_phone_number"),
        price_level=place.get("price_level"),
        price_range=place.get("price_range"),
        regular_opening_hours=place.get("regular_opening_hours"),
        current_opening_hours=place.get("current_opening_hours"),
        service_options=place.get("service_options") or {},
        google_maps_uri=place.get("google_maps_uri") or (
            "https://www.google.com/maps/search/?api=1"
            f"&query={place['name']}"
            f"&query_place_id={place['id']}"
        ),
        google_review_uri=f"https://search.google.com/local/writereview?placeid={place['id']}",
        selected_allergens=selected_allergens,
        score_summary=summary,
        evidence=evidence,
        review_snippets=[
            {
                "review_id": review["review_id"],
                "author_name": review.get("author_name"),
                "rating": review.get("rating"),
                "text": review.get("text", ""),
                "publish_time": review.get("publish_time"),
                "relative_publish_time": review.get("relative_publish_time"),
            }
            for review in place.get("reviews", [])
            if review.get("text")
        ][:6],
        review_source_summary=ReviewSourceSummary(
            google_review_count=google_review_count,
            expanded_review_count=len(apify_reviews),
            local_snapshot_review_count=0,
            analyzed_review_count=len([review for review in place.get("reviews", []) if review.get("text")]),
            displayed_review_count=min(6, len([review for review in place.get("reviews", []) if review.get("text")])),
            expanded_reviews_configured=bool(os.getenv("APIFY_TOKEN", "").strip()),
            expanded_review_provider="apify",
            expanded_review_status="loaded"
            if apify_reviews
            else ("deferred" if os.getenv("APIFY_TOKEN", "").strip() else "not_configured"),
        ),
        photos=place.get("photos", []),
        explanation=explanation,
        menu=menu if menu and menu.sections else None,
        agent_recommendation=agent_recommendation,
    )


async def get_place_menu_service(place_id: str) -> PlaceMenu:
    return load_place_menu(place_id)


async def get_place_reviews_service(place_id: str) -> list[PlaceReviewSnippet]:
    return load_cached_reviews(place_id)


async def create_review_refresh_job(place_id: str) -> ReviewRefreshJob:
    now = datetime.now(UTC).isoformat()
    try:
        reviews = fetch_apify_reviews(place_id)
        status = "complete"
        message = f"Captured {len(reviews)} Apify review{'s' if len(reviews) != 1 else ''}."
    except Exception as exc:  # noqa: BLE001 - external provider failures should become a job result
        reviews = []
        status = "failed"
        message = str(exc) or "Apify review fetch failed."

    job = ReviewRefreshJob(
        id=str(uuid4()),
        place_id=place_id,
        status=status,
        message=message,
        reviews_count=len(reviews),
        created_at=now,
        completed_at=datetime.now(UTC).isoformat(),
    )
    REVIEW_REFRESH_JOBS[job.id] = job
    return job


async def create_menu_refresh_job(
    place_id: str,
    restaurant_name: str | None = None,
    website_url: str | None = None,
    client: GooglePlacesClient | None = None,
) -> MenuRefreshJob:
    now = datetime.now(UTC).isoformat()
    resolved_name = restaurant_name
    resolved_url = website_url

    if not resolved_url and client is not None:
        place = client.get_place_details(place_id)
        resolved_name = resolved_name or place.get("name")
        resolved_url = place.get("website_uri")

    if not resolved_url:
        job = MenuRefreshJob(
            id=str(uuid4()),
            place_id=place_id,
            status="failed",
            message="No restaurant website was available for official menu ingestion.",
            created_at=now,
            completed_at=now,
        )
        MENU_REFRESH_JOBS[job.id] = job
        return job

    source = ingest_menu_from_website(
        restaurant_id=place_id,
        restaurant_name=resolved_name,
        website_url=resolved_url,
    )
    item_count = sum(len(section.items) for section in source.sections)
    status = "complete" if item_count else "failed"
    message = (
        f"Captured {item_count} menu item{'s' if item_count != 1 else ''} from {source.source_url}."
        if item_count
        else "No reliable dish-level menu items were extracted from the restaurant website or linked documents."
    )
    job = MenuRefreshJob(
        id=str(uuid4()),
        place_id=place_id,
        status=status,
        message=message,
        created_at=now,
        completed_at=datetime.now(UTC).isoformat(),
    )
    MENU_REFRESH_JOBS[job.id] = job
    return job


def merge_review_sources(google_reviews: list[dict], external_reviews: list[PlaceReviewSnippet]) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()

    for review in external_reviews:
        key = review.review_id or review.text
        if key in seen:
            continue
        seen.add(key)
        merged.append(
            {
                "review_id": review.review_id,
                "author_name": review.author_name,
                "rating": review.rating,
                "text": review.text,
                "publish_time": review.publish_time,
                "relative_publish_time": review.relative_publish_time,
            }
        )

    for review in google_reviews:
        text = review.get("text", "")
        key = review.get("review_id") or text
        if key in seen or not text:
            continue
        seen.add(key)
        merged.append(review)

    return merged


async def index_restaurant_menu_service(restaurant_id: str) -> SearchIndexResponse:
    return index_restaurant_menu(restaurant_id)


async def hybrid_search_service(payload: HybridSearchRequest) -> HybridSearchResponse:
    return hybrid_search_menu(payload)


async def create_restaurant_question(payload: AskRestaurantRequest) -> AskRestaurantResponse:
    allergen_text = ", ".join(item.value.replace("_", " ") for item in payload.allergens) or "my selected allergens"
    place_text = payload.place_name or "this restaurant"
    script = (
        f"Hi, I am checking whether {place_text} can accommodate {allergen_text}. "
        "Can you confirm ingredients, shared fryer or prep surfaces, and whether staff can prevent cross-contact?"
    )
    response = AskRestaurantResponse(
        id=str(uuid4()),
        status="queued",
        message="Question request saved. Outbound restaurant messaging can be enabled after account and contact workflows are connected.",
        suggested_script=payload.question or script,
    )
    ASK_REQUESTS[response.id] = response
    return response


async def get_user_profile() -> UserProfileResponse:
    return PROFILE


async def update_user_profile(profile: AllergyProfile) -> UserProfileResponse:
    PROFILE.profile = profile
    return PROFILE


async def save_place(place_id: str) -> UserProfileResponse:
    if place_id not in PROFILE.saved_places:
        PROFILE.saved_places.append(place_id)
    return PROFILE


async def remove_saved_place(place_id: str) -> UserProfileResponse:
    PROFILE.saved_places = [item for item in PROFILE.saved_places if item != place_id]
    return PROFILE
