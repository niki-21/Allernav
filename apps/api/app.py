from __future__ import annotations

import os

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from allernav_api.google_places import GooglePlacesClient, GooglePlacesError
from allernav_api.models import (
    AllergyProfile,
    AllergyTag,
    AskRestaurantRequest,
    AskRestaurantResponse,
    MenuRefreshJob,
    PlaceDetailsResponse,
    PlaceMenu,
    SearchRequest,
    SearchResponse,
    UserProfileResponse,
)
from allernav_api.service import (
    create_menu_refresh_job,
    create_restaurant_question,
    get_place_details_service,
    get_place_menu_service,
    get_user_profile,
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
    return {
        "ok": google_server,
        "service": "AllerNav API",
        "environment": {
            "google_places_server": google_server,
            "google_maps_client": google_client,
            "gemini": gemini,
            "supabase": supabase,
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


@app.post("/api/places/{place_id}/menu-refresh", response_model=MenuRefreshJob)
async def menu_refresh_endpoint(place_id: str) -> MenuRefreshJob:
    return await create_menu_refresh_job(place_id)


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
