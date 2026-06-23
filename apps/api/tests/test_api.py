from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from allernav_api.models import AllergyTag, LatLng, NearbySuggestionRequest, PlaceReviewSnippet, SearchRequest
from allernav_api.models import AllergyProfile, AnalyzeMenuRequest, MenuItem, MenuSection, MenuSource, SourceType
from allernav_api.agent_service import analyze_menu_service
from allernav_api.menu_ingestion import save_menu_source
from allernav_api.rag_service import restaurant_search_query, suggest_nearby_places_service
from fastapi.testclient import TestClient
from main import allowed_origins
from app import app
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
        with patch("allernav_api.service.load_cached_reviews", return_value=[]):
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

    def test_place_details_uses_cached_apify_reviews_when_available(self) -> None:
        with patch(
            "allernav_api.service.load_cached_reviews",
            return_value=[
                PlaceReviewSnippet(
                    review_id="apify-1",
                    author_name="Reviewer",
                    rating=1,
                    text="I have a sesame allergy and had a reaction after cross-contact.",
                    publish_time="2026-02-22T12:00:00+00:00",
                )
            ],
        ):
            response = asyncio.run(
                get_place_details_service(
                    "alpha",
                    allergens=[AllergyTag.SESAME],
                    client=FakePlacesClient(),
                )
            )

        self.assertEqual(response.review_snippets[0].review_id, "apify-1")
        self.assertEqual(response.score_summary.verdict.value, "high_risk")
        self.assertTrue(any(item.review_id == "apify-1" for item in response.evidence))
        self.assertEqual(response.review_source_summary.expanded_review_status, "loaded")

    def test_missing_reviews_is_handled(self) -> None:
        class NoReviewClient(FakePlacesClient):
            def get_place_details(self, place_id: str):  # noqa: ANN001
                place = super().get_place_details(place_id)
                place["reviews"] = []
                return place

        with patch("allernav_api.service.load_cached_reviews", return_value=[]):
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

    def test_menu_refresh_endpoint_stores_and_returns_menu(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "menus.sqlite"
            os.environ["ALLERNAV_MENU_DB"] = str(db_path)

            def fake_ingest(**kwargs):  # noqa: ANN003, ANN202
                source = MenuSource(
                    source_type=SourceType.RESTAURANT_WEBSITE,
                    source_url=kwargs["website_url"],
                    reliability=0.8,
                    sections=[
                        MenuSection(
                            title="Bowls",
                            items=[MenuItem(name="Tomato Rice Bowl", description="Rice, tomato, greens.")],
                        )
                    ],
                )
                save_menu_source(
                    restaurant_id=kwargs["restaurant_id"],
                    restaurant_name=kwargs["restaurant_name"],
                    source=source,
                    db_path=db_path,
                )
                return source

            with patch("allernav_api.service.ingest_menu_from_website", side_effect=fake_ingest):
                client = TestClient(app)
                refresh = client.post(
                    "/api/places/alpha/menu-refresh",
                    params={"restaurant_name": "Alpha", "website_url": "https://example.com/menu"},
                )
                menu = client.get("/api/places/alpha/menu")

            os.environ.pop("ALLERNAV_MENU_DB", None)

        self.assertEqual(refresh.status_code, 200)
        self.assertEqual(refresh.json()["status"], "complete")
        self.assertEqual(menu.status_code, 200)
        self.assertEqual(menu.json()["sections"][0]["items"][0]["name"], "Tomato Rice Bowl")

    def test_nearby_rag_suggestions_retrieve_stored_menu_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "menus.sqlite"
            os.environ["ALLERNAV_MENU_DB"] = str(db_path)
            os.environ.pop("GEMINI_API_KEY", None)
            save_menu_source(
                restaurant_id="alpha",
                restaurant_name="Alpha Cafe",
                source=MenuSource(
                    source_type=SourceType.RESTAURANT_WEBSITE,
                    source_url="https://example.com/menu",
                    reliability=0.8,
                    sections=[
                        MenuSection(
                            title="Bowls",
                            items=[
                                MenuItem(name="Tomato Rice Bowl", description="Rice, tomato, greens."),
                                MenuItem(name="Peanut Noodles", description="Wheat noodles, peanut sauce."),
                            ],
                        )
                    ],
                ),
                db_path=db_path,
            )

            response = asyncio.run(
                suggest_nearby_places_service(
                    NearbySuggestionRequest(
                        question="Where should I start for peanut allergy?",
                        allergens=[AllergyTag.PEANUT],
                        candidate_place_ids=["alpha"],
                    ),
                    client=FakePlacesClient(),
                )
            )
            os.environ.pop("ALLERNAV_MENU_DB", None)

        self.assertEqual(response.places[0].place.id, "alpha")
        self.assertGreaterEqual(len(response.evidence), 1)
        self.assertIn("verification", response.answer.lower())

    def test_nearby_rag_normalizes_broad_assistant_questions_to_restaurants(self) -> None:
        self.assertEqual(restaurant_search_query("Suggest nearby places here"), "restaurants")
        self.assertEqual(restaurant_search_query("Suggest sushi options nearby"), "sushi restaurants")


if __name__ == "__main__":
    unittest.main()
