from __future__ import annotations

import asyncio
import unittest

from allernav_api.models import AllergyTag, LatLng, SearchRequest
from allernav_api.models import AllergyProfile, AnalyzeMenuRequest, MenuSource, SourceType
from allernav_api.agent_service import analyze_menu_service
from main import allowed_origins
from allernav_api.service import get_place_details_service, search_places_service


class FakePlacesClient:
    def search_places(self, query: str, center: LatLng, max_results: int = 12):  # noqa: ANN001
        return [
            {
                "id": "alpha",
                "name": "Alpha Cafe",
                "address": "123 Main St",
                "location": {"lat": center.lat, "lng": center.lng},
                "rating": 4.5,
                "user_rating_count": 42,
                "primary_type": "restaurant",
            }
        ]

    def get_place_details(self, place_id: str):  # noqa: ANN001
        return {
            "id": place_id,
            "name": "Alpha Cafe",
            "address": "123 Main St",
            "location": {"lat": 38.9, "lng": -77.0},
            "rating": 4.5,
            "user_rating_count": 42,
            "primary_type": "restaurant",
            "website_uri": "https://example.com",
            "editorial_summary": "Modern cafe",
            "reviews": [
                {
                    "review_id": "1",
                    "rating": 5,
                    "text": "The staff understood my peanut allergy and double checked the fryer.",
                    "publish_time": "2026-02-20T12:00:00Z",
                }
            ],
        }


class ApiTests(unittest.TestCase):
    def test_allowed_origins_include_localhost_defaults(self) -> None:
        origins = allowed_origins()
        self.assertIn("http://localhost:3000", origins)
        self.assertIn("http://127.0.0.1:3000", origins)

    def test_search_response_shape(self) -> None:
        payload = SearchRequest(
            query="ramen",
            center=LatLng(lat=38.9, lng=-77.0),
            allergens=[AllergyTag.PEANUT],
        )

        response = asyncio.run(search_places_service(payload, client=FakePlacesClient()))

        dumped = response.model_dump()
        self.assertEqual(dumped["query"], "ramen")
        self.assertEqual(dumped["center"]["lat"], 38.9)
        self.assertEqual(dumped["places"][0]["id"], "alpha")
        self.assertEqual(dumped["allergens"], ["peanut"])

    def test_place_details_response_shape(self) -> None:
        response = asyncio.run(
            get_place_details_service(
                "alpha",
                allergens=[AllergyTag.PEANUT],
                client=FakePlacesClient(),
            )
        )

        dumped = response.model_dump()
        self.assertEqual(dumped["id"], "alpha")
        self.assertEqual(dumped["selected_allergens"], ["peanut"])
        self.assertIn("score_summary", dumped)
        self.assertGreaterEqual(len(dumped["evidence"]), 1)
        self.assertIn("explanation", dumped)

    def test_missing_reviews_is_handled(self) -> None:
        class NoReviewClient(FakePlacesClient):
            def get_place_details(self, place_id: str):  # noqa: ANN001
                place = super().get_place_details(place_id)
                place["reviews"] = []
                return place

        response = asyncio.run(
            get_place_details_service(
                "alpha",
                allergens=[AllergyTag.PEANUT],
                client=NoReviewClient(),
            )
        )

        self.assertEqual(response.score_summary.evidence_count, 0)
        self.assertEqual(response.score_summary.verdict.value, "use_caution")

    def test_analyze_menu_service_returns_source_backed_recommendation(self) -> None:
        response = asyncio.run(
            analyze_menu_service(
                AnalyzeMenuRequest(
                    restaurant_name="Demo Pasta",
                    profile=AllergyProfile(allergens=[AllergyTag.DAIRY]),
                    menu_sources=[
                        MenuSource(
                            source_type=SourceType.OFFICIAL_MENU,
                            source_url="https://example.com/menu",
                            reliability=0.9,
                            raw_text="Chicken Alfredo - pasta with cream sauce, butter, and parmesan",
                        )
                    ],
                )
            )
        )

        dumped = response.model_dump()
        self.assertEqual(dumped["overall_risk"], "high")
        self.assertEqual(dumped["recommended_action"], "avoid")
        self.assertGreaterEqual(len(dumped["evidence"]), 1)


if __name__ == "__main__":
    unittest.main()
