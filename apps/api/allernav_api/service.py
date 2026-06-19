from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from .agent_graph import run_dining_safety_graph
from .google_places import GooglePlacesClient
from .menu_ingestion import ingest_menu_from_website, load_place_menu
from .models import (
    AllergyProfile,
    AllergyTag,
    AskRestaurantRequest,
    AskRestaurantResponse,
    LatLng,
    MenuRefreshJob,
    PlaceDetailsResponse,
    PlaceMenu,
    RestaurantContext,
    SearchRequest,
    SearchResponse,
    UserProfileResponse,
)
from .scoring import analyze_place


DEFAULT_CENTER = LatLng(lat=40.741895, lng=-73.989308)
MENU_REFRESH_JOBS: dict[str, MenuRefreshJob] = {}
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
    summary, evidence, explanation = analyze_place(place, selected_allergens)
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
        google_maps_uri=(
            "https://www.google.com/maps/search/?api=1"
            f"&query={place['name']}"
            f"&query_place_id={place['id']}"
        ),
        google_review_uri=f"https://search.google.com/local/writereview?placeid={place['id']}",
        selected_allergens=selected_allergens,
        score_summary=summary,
        evidence=evidence,
        explanation=explanation,
        agent_recommendation=agent_recommendation,
    )


async def get_place_menu_service(place_id: str) -> PlaceMenu:
    return load_place_menu(place_id)


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
            message="Menu refresh needs a restaurant website URL before official menu ingestion can run.",
            created_at=now,
            completed_at=datetime.now(UTC).isoformat(),
        )
        MENU_REFRESH_JOBS[job.id] = job
        return job

    source = ingest_menu_from_website(
        restaurant_id=place_id,
        restaurant_name=resolved_name,
        website_url=resolved_url,
    )
    status = "complete" if source.sections else "failed"
    item_count = sum(len(section.items) for section in source.sections)
    job = MenuRefreshJob(
        id=str(uuid4()),
        place_id=place_id,
        status=status,
        message=(
            f"Menu refresh complete. Captured {item_count} menu item{'' if item_count == 1 else 's'} from {source.source_url}."
            if item_count
            else "Menu refresh ran, but no structured official menu items were extracted."
        ),
        created_at=now,
        completed_at=datetime.now(UTC).isoformat(),
    )
    MENU_REFRESH_JOBS[job.id] = job
    return job


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
