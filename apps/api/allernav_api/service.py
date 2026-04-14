from __future__ import annotations

from .google_places import GooglePlacesClient
from .models import AllergyTag, LatLng, PlaceDetailsResponse, SearchRequest, SearchResponse
from .scoring import analyze_place


DEFAULT_CENTER = LatLng(lat=40.741895, lng=-73.989308)


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
        selected_allergens=selected_allergens,
        score_summary=summary,
        evidence=evidence,
        explanation=explanation,
    )

