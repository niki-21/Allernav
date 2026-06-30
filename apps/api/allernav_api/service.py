from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

from .agent_graph import run_dining_safety_graph
from .azure_search import hybrid_search_menu, index_restaurant_menu
from .google_places import GooglePlacesClient
from .menu_ingestion import (
    common_menu_url_candidates,
    candidate_url_priority,
    extract_candidate_menu_urls,
    fetch_html_url,
    ingest_menu_from_website,
    load_menu_source,
    load_place_menu,
)
from .menu_indexing import finish_menu_index
from .menu_job_queue import MenuRefreshMessage, enqueue_menu_refresh, service_bus_menu_queue_configured
from .menu_risk import classify_place_menu
from .squarespace_menu import MenuImageSet, discover_squarespace_menu_images
from . import supabase_store
from .models import (
    AllergyProfile,
    AllergyTag,
    HybridSearchRequest,
    HybridSearchResponse,
    IngestionTraceStep,
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
MENU_INDEX_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="allernav-menu-index")


def menu_refresh_mode() -> str:
    value = os.getenv("MENU_REFRESH_MODE", "auto").strip().lower()
    return value if value in {"local", "durable", "auto"} else "auto"


def production_environment() -> bool:
    return (
        os.getenv("ENVIRONMENT", "").strip().lower() == "production"
        or os.getenv("VERCEL_ENV", "").strip().lower() == "production"
    )


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


async def get_place_menu_service(place_id: str, allergens: list[AllergyTag] | None = None) -> PlaceMenu:
    return classify_place_menu(load_place_menu(place_id), allergens or [])


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
    allow_local_fallback: bool = True,
) -> MenuRefreshJob:
    now = datetime.now(UTC).isoformat()
    resolved_name = restaurant_name
    resolved_url = website_url
    place = {}

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

    refresh_mode = menu_refresh_mode()
    durable_configured = service_bus_menu_queue_configured() and supabase_store.configured()
    if refresh_mode != "local" and durable_configured:
        image_set = _discover_squarespace_image_set(resolved_url) if allow_local_fallback else None
        document_urls = image_set.document_urls if image_set else []
        job = MenuRefreshJob(
            id=str(uuid4()),
            place_id=place_id,
            status="queued",
            message=(
                f"Queued OCR for {len(document_urls)} official menu images."
                if document_urls
                else "Queued durable menu discovery."
            ),
            document_urls=document_urls,
            total_documents=len(document_urls),
            processed_documents=0,
            menu_version=image_set.version if image_set else None,
            trace=[
                IngestionTraceStep(
                    id="source_discovery",
                    label="Discover menu sources",
                    status="complete",
                    detail=(
                        f"Selected {len(document_urls)} images from menu edition {image_set.version or 'unknown'}."
                        if image_set
                        else "The durable worker will continue menu discovery."
                    ),
                    provider="squarespace_image_discovery" if image_set else "restaurant_website",
                    source_url=resolved_url,
                    item_count=len(document_urls),
                ),
                *(
                    [
                        IngestionTraceStep(
                            id="source_identity_check",
                            label="Verify menu source identity",
                            status="accepted",
                            detail="Accepted menu images because they were linked from the official restaurant website.",
                            provider="source_identity_validator",
                            source_url=image_set.source_url,
                            item_count=len(document_urls),
                        )
                    ]
                    if image_set
                    else []
                ),
            ],
            created_at=now,
        )
        MENU_REFRESH_JOBS[job.id] = job
        if not supabase_store.save_menu_refresh_job(job):
            storage_reason = supabase_store.last_error() or "Supabase rejected the menu refresh job."
            if allow_local_fallback and (refresh_mode == "auto" or not production_environment()):
                return _create_local_menu_refresh_job(
                    place_id=place_id,
                    restaurant_name=resolved_name,
                    website_url=resolved_url,
                    restaurant_address=place.get("address"),
                    fallback_detail=(
                        "Cloud job could not be saved, so this scan ran directly. "
                        f"Reason: {storage_reason}"
                    ),
                )
            failed = job.model_copy(
                update={
                    "status": "failed",
                    "message": "Could not persist the durable menu refresh job in Supabase.",
                    "completed_at": datetime.now(UTC).isoformat(),
                }
            )
            MENU_REFRESH_JOBS[job.id] = failed
            return failed
        try:
            enqueue_menu_refresh(
                MenuRefreshMessage(
                    version=1,
                    job_id=job.id,
                    place_id=place_id,
                    restaurant_name=resolved_name,
                    website_url=image_set.source_url if image_set else resolved_url,
                    document_urls=document_urls,
                    menu_version=image_set.version if image_set else None,
                )
            )
        except RuntimeError as exc:
            if allow_local_fallback and (refresh_mode == "auto" or not production_environment()):
                failed = job.model_copy(
                    update={
                        "status": "failed",
                        "message": f"Durable queue enqueue failed; local fallback started. {exc}",
                        "completed_at": datetime.now(UTC).isoformat(),
                    }
                )
                MENU_REFRESH_JOBS[job.id] = failed
                supabase_store.save_menu_refresh_job(failed)
                return _create_local_menu_refresh_job(
                    place_id=place_id,
                    restaurant_name=resolved_name,
                    website_url=resolved_url,
                    restaurant_address=place.get("address"),
                    fallback_detail=f"Durable queue enqueue failed; continued locally. {exc}",
                )
            failed = job.model_copy(
                update={
                    "status": "failed",
                    "message": str(exc),
                    "completed_at": datetime.now(UTC).isoformat(),
                }
            )
            MENU_REFRESH_JOBS[job.id] = failed
            supabase_store.save_menu_refresh_job(failed)
            return failed
        return job

    if refresh_mode == "durable" and production_environment():
        job = MenuRefreshJob(
            id=str(uuid4()),
            place_id=place_id,
            status="failed",
            message="Durable menu refresh requires configured Supabase and Azure Service Bus.",
            created_at=now,
            completed_at=now,
        )
        MENU_REFRESH_JOBS[job.id] = job
        return job

    if not allow_local_fallback:
        job = MenuRefreshJob(
            id=str(uuid4()),
            place_id=place_id,
            status="failed",
            message="A durable menu refresh queue is required for background scanning.",
            created_at=now,
            completed_at=now,
        )
        MENU_REFRESH_JOBS[job.id] = job
        return job

    return _create_local_menu_refresh_job(
        place_id=place_id,
        restaurant_name=resolved_name,
        website_url=resolved_url,
        restaurant_address=place.get("address"),
        fallback_detail=(
            "Durable services were unavailable; continued with local ingestion."
            if refresh_mode == "durable" and not durable_configured
            else None
        ),
    )


def _create_local_menu_refresh_job(
    *,
    place_id: str,
    restaurant_name: str | None,
    website_url: str,
    restaurant_address: str | None,
    fallback_detail: str | None = None,
) -> MenuRefreshJob:
    now = datetime.now(UTC).isoformat()
    trace: list[IngestionTraceStep] = []
    if fallback_detail:
        trace.append(
            IngestionTraceStep(
                id="refresh_mode",
                label="Select refresh mode",
                status="complete",
                detail=fallback_detail,
                provider="direct_menu_scan",
            )
        )
    source = ingest_menu_from_website(
        restaurant_id=place_id,
        restaurant_name=restaurant_name,
        website_url=website_url,
        restaurant_address=restaurant_address,
        trace=trace,
    )
    item_count = sum(len(section.items) for section in source.sections)
    needs_background_refresh = any(step.status == "deferred" for step in trace)
    status = "complete" if item_count else ("needs_background_refresh" if needs_background_refresh else "failed")
    message = (
        f"Captured {item_count} menu item{'s' if item_count != 1 else ''} from {source.source_url}."
        if item_count
        else (
            "Menu candidates were found, but the interactive scan reached its time budget. A background refresh is needed."
            if needs_background_refresh
            else (
                "No reliable dish-level menu items were extracted. "
                f"Last checked source: {source.source_url or website_url}."
            )
        )
    )
    if item_count:
        trace.append(
            IngestionTraceStep(
                id="menu_extracted",
                label="Menu extracted",
                status="complete",
                detail=f"Published {item_count} dish-level menu items for immediate review.",
                provider=source.extraction_method or "menu_ingestion",
                item_count=item_count,
            )
        )
        trace.append(
            IngestionTraceStep(
                id="search_index",
                label="Index menu evidence",
                status="pending",
                detail="Menu evidence is available while the RAG index updates in the background.",
                provider="azure_ai_search",
                item_count=item_count,
            )
        )
    else:
        trace.append(
            IngestionTraceStep(
                id="search_index",
                label="Index menu evidence",
                status="skipped",
                detail="Indexing was skipped because no dish-level menu items were extracted.",
                provider="azure_ai_search",
                item_count=0,
            )
        )

    job = MenuRefreshJob(
        id=str(uuid4()),
        place_id=place_id,
        status=status,
        message=message,
        item_count=item_count,
        source_url=source.source_url,
        content_type=source.content_type,
        extraction_method=source.extraction_method,
        page_count=source.page_count,
        extraction_confidence=source.extraction_confidence,
        indexing_status="pending" if item_count else "skipped",
        trace=trace,
        created_at=now,
        completed_at=datetime.now(UTC).isoformat(),
    )
    MENU_REFRESH_JOBS[job.id] = job
    if item_count:
        MENU_INDEX_EXECUTOR.submit(_finish_local_menu_index, job.id)
    return job


async def get_menu_refresh_job_service(job_id: str) -> MenuRefreshJob | None:
    durable = supabase_store.load_menu_refresh_job(job_id)
    if durable:
        MENU_REFRESH_JOBS[job_id] = durable
        return durable
    return MENU_REFRESH_JOBS.get(job_id)


def _finish_local_menu_index(job_id: str) -> None:
    current = MENU_REFRESH_JOBS.get(job_id)
    if not current:
        return

    def persist(job: MenuRefreshJob) -> None:
        MENU_REFRESH_JOBS[job_id] = job
        if supabase_store.configured():
            supabase_store.save_menu_refresh_job(job)

    finish_menu_index(current, persist=persist, indexer=index_restaurant_menu)


def _discover_squarespace_image_set(website_url: str) -> MenuImageSet | None:
    homepage = fetch_html_url(website_url)
    if not homepage:
        return None
    image_set = discover_squarespace_menu_images(homepage, website_url)
    if image_set:
        return image_set
    linked_candidates = sorted(
        set(extract_candidate_menu_urls(homepage, website_url)),
        key=candidate_url_priority,
    )
    candidates = [*linked_candidates]
    for candidate in common_menu_url_candidates(website_url):
        if candidate not in candidates:
            candidates.append(candidate)
    checked: set[str] = {website_url}
    for candidate in candidates:
        if candidate in checked or len(checked) >= 5:
            continue
        checked.add(candidate)
        page = fetch_html_url(candidate)
        if not page:
            continue
        image_set = discover_squarespace_menu_images(page, candidate)
        if image_set:
            return image_set
    return None


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
