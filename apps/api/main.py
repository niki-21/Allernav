from __future__ import annotations

import os

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from allernav_api.google_places import GooglePlacesClient, GooglePlacesError
from allernav_api.models import AllergyTag, PlaceDetailsResponse, SearchRequest, SearchResponse
from allernav_api.service import get_place_details_service, search_places_service


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


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


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
