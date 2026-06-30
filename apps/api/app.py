from __future__ import annotations

import os

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from allernav_api.google_places import GooglePlacesClient, GooglePlacesError
from allernav_api.models import (
    AllergyProfile,
    AllergyTag,
    AnalyzeMenuRequest,
    AnalyzeRestaurantRequest,
    AskRestaurantRequest,
    AskRestaurantResponse,
    ChatRequest,
    ChatResponse,
    EvidenceFragment,
    FeedbackEvent,
    FeedbackResponse,
    HybridSearchRequest,
    HybridSearchResponse,
    MenuRefreshJob,
    NearbySuggestionRequest,
    NearbySuggestionResponse,
    PlaceDetailsResponse,
    PlaceMenu,
    PlaceReviewSnippet,
    RecommendationResult,
    RecommendDishesRequest,
    ReviewRefreshJob,
    SearchIndexResponse,
    SearchRequest,
    SearchResponse,
    UserProfileResponse,
)
from allernav_api.rag_service import azure_openai_chat_configured, suggest_nearby_places_service
from allernav_api.agent_service import (
    analyze_menu_service,
    analyze_restaurant_service,
    chat_service,
    feedback_service,
    recommend_dishes_service,
    restaurant_evidence_service,
)
from allernav_api.service import (
    create_menu_refresh_job,
    get_menu_refresh_job_service,
    create_review_refresh_job,
    create_restaurant_question,
    get_place_details_service,
    get_place_menu_service,
    get_place_reviews_service,
    get_user_profile,
    hybrid_search_service,
    index_restaurant_menu_service,
    remove_saved_place,
    save_place,
    search_places_service,
    update_user_profile,
)


def get_places_client() -> GooglePlacesClient:
    return GooglePlacesClient()


def allowed_origins() -> list[str]:
    origins = {
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    }
    configured = os.getenv("FRONTEND_ORIGIN", "")
    for item in configured.split(","):
        value = item.strip()
        if value:
            origins.add(value)
    return sorted(origins)


app = FastAPI(title="Allernav API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "Allernav API", "status": "ok", "health": "/health"}


@app.get("/health")
def health() -> dict[str, object]:
    google_server = bool(os.getenv("GOOGLE_PLACES_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY"))
    google_client = bool(os.getenv("NEXT_PUBLIC_GOOGLE_MAPS_API_KEY"))
    gemini = bool(os.getenv("GEMINI_API_KEY"))
    supabase = bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
    azure_document_intelligence = bool(
        os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT") and os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY")
    )
    azure_search = bool(
        os.getenv("AZURE_SEARCH_ENDPOINT")
        and os.getenv("AZURE_SEARCH_API_KEY")
        and os.getenv("AZURE_SEARCH_INDEX_NAME")
    )
    azure_openai_embeddings = bool(
        os.getenv("AZURE_OPENAI_ENDPOINT")
        and os.getenv("AZURE_OPENAI_API_KEY")
        and os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
    )
    azure_openai_chat = azure_openai_chat_configured()
    azure_service_bus_menu = bool(os.getenv("AZURE_SERVICE_BUS_SEND_CONNECTION_STRING"))
    apify = bool(os.getenv("APIFY_TOKEN"))
    apify_menu_discovery = apify and os.getenv("APIFY_MENU_DISCOVERY_ENABLED", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    langsmith = os.getenv("LANGSMITH_TRACING", "").lower() == "true" and bool(os.getenv("LANGSMITH_API_KEY"))
    return {
        "ok": google_server,
        "service": "AllerNav API",
        "environment": {
            "google_places_server": google_server,
            "google_maps_client": google_client,
            "gemini": gemini,
            "supabase": supabase,
            "azure_document_intelligence": azure_document_intelligence,
            "azure_search": azure_search,
            "azure_openai_embeddings": azure_openai_embeddings,
            "azure_openai_chat": azure_openai_chat,
            "azure_service_bus_menu": azure_service_bus_menu,
            "durable_menu_refresh": azure_service_bus_menu and supabase,
            "apify_reviews": apify,
            "apify_menu_discovery": apify_menu_discovery,
            "langsmith": langsmith,
        },
    }


@app.post("/api/search", response_model=SearchResponse)
async def search_places_endpoint(
    payload: SearchRequest,
    client: GooglePlacesClient = Depends(get_places_client),
) -> SearchResponse:
    try:
        return await search_places_service(payload, client)
    except GooglePlacesError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/analyze-restaurant", response_model=RecommendationResult)
@app.post("/api/analyze-restaurant", response_model=RecommendationResult)
async def analyze_restaurant_endpoint(payload: AnalyzeRestaurantRequest) -> RecommendationResult:
    return await analyze_restaurant_service(payload)


@app.post("/analyze-menu", response_model=RecommendationResult)
@app.post("/api/analyze-menu", response_model=RecommendationResult)
async def analyze_menu_endpoint(payload: AnalyzeMenuRequest) -> RecommendationResult:
    return await analyze_menu_service(payload)


@app.post("/recommend-dishes", response_model=RecommendationResult)
@app.post("/api/recommend-dishes", response_model=RecommendationResult)
async def recommend_dishes_endpoint(payload: RecommendDishesRequest) -> RecommendationResult:
    return await recommend_dishes_service(payload)


@app.post("/chat", response_model=ChatResponse)
@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest) -> ChatResponse:
    return await chat_service(payload)


@app.post("/nearby-suggestions", response_model=NearbySuggestionResponse)
@app.post("/api/nearby-suggestions", response_model=NearbySuggestionResponse)
@app.post("/api/rag/nearby-suggestions", response_model=NearbySuggestionResponse)
async def nearby_suggestions_endpoint(
    payload: NearbySuggestionRequest,
) -> NearbySuggestionResponse:
    return await suggest_nearby_places_service(payload)


@app.post("/feedback", response_model=FeedbackResponse)
@app.post("/api/feedback", response_model=FeedbackResponse)
async def feedback_endpoint(payload: FeedbackEvent) -> FeedbackResponse:
    return await feedback_service(payload)


@app.get("/restaurants/{restaurant_id}/evidence", response_model=list[EvidenceFragment])
@app.get("/api/restaurants/{restaurant_id}/evidence", response_model=list[EvidenceFragment])
async def restaurant_evidence_endpoint(restaurant_id: str) -> list[EvidenceFragment]:
    return await restaurant_evidence_service(restaurant_id)


@app.post("/restaurants/{restaurant_id}/search-index", response_model=SearchIndexResponse)
@app.post("/api/restaurants/{restaurant_id}/search-index", response_model=SearchIndexResponse)
async def restaurant_search_index_endpoint(restaurant_id: str) -> SearchIndexResponse:
    return await index_restaurant_menu_service(restaurant_id)


@app.post("/hybrid-search", response_model=HybridSearchResponse)
@app.post("/api/hybrid-search", response_model=HybridSearchResponse)
@app.post("/api/search/hybrid", response_model=HybridSearchResponse)
async def hybrid_search_endpoint(payload: HybridSearchRequest) -> HybridSearchResponse:
    return await hybrid_search_service(payload)


@app.get("/api/places/{place_id}", response_model=PlaceDetailsResponse)
async def place_details_endpoint(
    place_id: str,
    allergens: list[AllergyTag] = Query(default_factory=list),
    client: GooglePlacesClient = Depends(get_places_client),
) -> PlaceDetailsResponse:
    try:
        return await get_place_details_service(place_id, allergens, client)
    except GooglePlacesError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/places/{place_id}/menu", response_model=PlaceMenu)
async def place_menu_endpoint(place_id: str) -> PlaceMenu:
    return await get_place_menu_service(place_id)


@app.get("/api/places/{place_id}/reviews", response_model=list[PlaceReviewSnippet])
async def place_reviews_endpoint(place_id: str) -> list[PlaceReviewSnippet]:
    return await get_place_reviews_service(place_id)


@app.post("/api/places/{place_id}/reviews-refresh", response_model=ReviewRefreshJob)
async def reviews_refresh_endpoint(place_id: str) -> ReviewRefreshJob:
    return await create_review_refresh_job(place_id)


@app.post("/api/places/{place_id}/menu-refresh", response_model=MenuRefreshJob, status_code=202)
async def menu_refresh_endpoint(
    place_id: str,
    restaurant_name: str | None = Query(default=None),
    website_url: str | None = Query(default=None),
    client: GooglePlacesClient = Depends(get_places_client),
) -> MenuRefreshJob:
    try:
        return await create_menu_refresh_job(place_id, restaurant_name, website_url, client)
    except GooglePlacesError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/menu-refresh-jobs/{job_id}", response_model=MenuRefreshJob)
async def menu_refresh_job_endpoint(job_id: str) -> MenuRefreshJob:
    job = await get_menu_refresh_job_service(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Menu refresh job not found.")
    return job


@app.post("/api/places/{place_id}/ask", response_model=AskRestaurantResponse)
async def ask_restaurant_endpoint(place_id: str, payload: AskRestaurantRequest) -> AskRestaurantResponse:
    return await create_restaurant_question(payload.model_copy(update={"place_id": place_id}))


@app.get("/api/me/profile", response_model=UserProfileResponse)
async def get_profile_endpoint() -> UserProfileResponse:
    return await get_user_profile()


@app.put("/api/me/profile", response_model=UserProfileResponse)
async def update_profile_endpoint(profile: AllergyProfile) -> UserProfileResponse:
    return await update_user_profile(profile)


@app.post("/api/me/saved-places/{place_id}", response_model=UserProfileResponse)
async def save_place_endpoint(place_id: str) -> UserProfileResponse:
    return await save_place(place_id)


@app.delete("/api/me/saved-places/{place_id}", response_model=UserProfileResponse)
async def remove_saved_place_endpoint(place_id: str) -> UserProfileResponse:
    return await remove_saved_place(place_id)
