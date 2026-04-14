from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request

from .models import LatLng, PlaceListItem


GOOGLE_PLACES_BASE_URL = "https://places.googleapis.com/v1"


class GooglePlacesError(RuntimeError):
    """Raised when Google Places cannot be queried successfully."""


@dataclass
class CacheEntry:
    payload: dict[str, Any]
    expires_at: float


class GooglePlacesClient:
    def __init__(self, api_key: str | None = None, base_url: str = GOOGLE_PLACES_BASE_URL) -> None:
        self.api_key = api_key or os.getenv("GOOGLE_MAPS_API_KEY") or os.getenv("GOOGLE_PLACES_API_KEY") or os.getenv("NEXT_PUBLIC_GOOGLE_MAPS_API_KEY")
        self.base_url = base_url.rstrip("/")
        self._place_cache: dict[str, CacheEntry] = {}

    def search_places(self, query: str, center: LatLng, max_results: int = 12) -> list[PlaceListItem]:
        if query.strip():
            endpoint = "/places:searchText"
            body = {
                "textQuery": query.strip(),
                "pageSize": max_results,
                "includedType": "restaurant",
                "strictTypeFiltering": False,
                "locationBias": {
                    "circle": {
                        "center": {"latitude": center.lat, "longitude": center.lng},
                        "radius": 5000.0,
                    }
                },
            }
            field_mask = ",".join(
                [
                    "places.id",
                    "places.displayName",
                    "places.location",
                    "places.formattedAddress",
                    "places.rating",
                    "places.userRatingCount",
                    "places.primaryType",
                ]
            )
        else:
            endpoint = "/places:searchNearby"
            body = {
                "includedTypes": ["restaurant"],
                "maxResultCount": max_results,
                "locationRestriction": {
                    "circle": {
                        "center": {"latitude": center.lat, "longitude": center.lng},
                        "radius": 5000.0,
                    }
                },
            }
            field_mask = ",".join(
                [
                    "places.id",
                    "places.displayName",
                    "places.location",
                    "places.formattedAddress",
                    "places.rating",
                    "places.userRatingCount",
                    "places.primaryType",
                ]
            )

        payload = self._request_json(
            f"{self.base_url}{endpoint}",
            method="POST",
            body=body,
            field_mask=field_mask,
        )

        places = payload.get("places", [])
        return [self._parse_place_summary(place) for place in places if place.get("id") and place.get("location")]

    def get_place_details(self, place_id: str) -> dict[str, Any]:
        cached = self._place_cache.get(place_id)
        now = time.time()
        if cached and cached.expires_at > now:
            return cached.payload

        field_mask = ",".join(
            [
                "id",
                "displayName",
                "formattedAddress",
                "location",
                "rating",
                "userRatingCount",
                "websiteUri",
                "primaryType",
                "editorialSummary",
                "reviews",
            ]
        )
        payload = self._request_json(
            f"{self.base_url}/places/{parse.quote(place_id)}",
            method="GET",
            field_mask=field_mask,
        )
        normalized = self._parse_place_details(payload)
        self._place_cache[place_id] = CacheEntry(payload=normalized, expires_at=now + 600)
        return normalized

    def _request_json(
        self,
        url: str,
        *,
        method: str,
        field_mask: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise GooglePlacesError("Missing Google Places API key. Set GOOGLE_MAPS_API_KEY or GOOGLE_PLACES_API_KEY.")

        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("X-Goog-Api-Key", self.api_key)
        req.add_header("X-Goog-FieldMask", field_mask)

        try:
            with request.urlopen(req, timeout=12) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise GooglePlacesError(f"Google Places request failed with {exc.code}: {detail or exc.reason}") from exc
        except error.URLError as exc:
            raise GooglePlacesError(f"Unable to reach Google Places: {exc.reason}") from exc

        return json.loads(raw)

    def _parse_place_summary(self, place: dict[str, Any]) -> PlaceListItem:
        location = place.get("location", {})
        return PlaceListItem(
            id=place["id"],
            name=(place.get("displayName") or {}).get("text") or "Unknown place",
            address=place.get("formattedAddress"),
            location=LatLng(
                lat=location.get("latitude", 0.0),
                lng=location.get("longitude", 0.0),
            ),
            rating=place.get("rating"),
            user_rating_count=place.get("userRatingCount"),
            primary_type=place.get("primaryType"),
        )

    def _parse_place_details(self, place: dict[str, Any]) -> dict[str, Any]:
        location = place.get("location", {})
        reviews = []
        for index, review in enumerate(place.get("reviews", [])):
            text_payload = review.get("originalText") or review.get("text") or {}
            reviews.append(
                {
                    "review_id": review.get("name") or f"review-{index}",
                    "author_name": (review.get("authorAttribution") or {}).get("displayName"),
                    "rating": review.get("rating"),
                    "text": text_payload.get("text", ""),
                    "publish_time": review.get("publishTime"),
                    "relative_publish_time": review.get("relativePublishTimeDescription"),
                }
            )

        return {
            "id": place["id"],
            "name": (place.get("displayName") or {}).get("text") or "Unknown place",
            "address": place.get("formattedAddress"),
            "location": {
                "lat": location.get("latitude", 0.0),
                "lng": location.get("longitude", 0.0),
            },
            "rating": place.get("rating"),
            "user_rating_count": place.get("userRatingCount"),
            "website_uri": place.get("websiteUri"),
            "primary_type": place.get("primaryType"),
            "editorial_summary": ((place.get("editorialSummary") or {}).get("text")),
            "reviews": reviews,
        }

