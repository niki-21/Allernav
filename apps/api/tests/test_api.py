from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from allernav_api.models import (
    AllergyTag,
    IngestionTraceStep,
    HybridSearchResult,
    LatLng,
    MenuRefreshJob,
    NearbySuggestionRequest,
    NearbyPlaceSuggestion,
    PlaceListItem,
    PlaceReviewSnippet,
    SearchRequest,
)
from allernav_api.models import AllergyProfile, AnalyzeMenuRequest, MenuItem, MenuSection, MenuSource, SourceType
from allernav_api.agent_service import analyze_menu_service
from allernav_api.menu_ingestion import save_menu_source
from allernav_api.rag_service import (
    clean_llm_answer,
    generate_azure_openai_answer,
    generate_nearby_answer,
    restaurant_search_query,
    suggest_nearby_places_service,
)
from fastapi.testclient import TestClient
from main import allowed_origins
from app import app
from allernav_api.service import create_menu_refresh_job, get_place_details_service, menu_refresh_mode, search_places_service


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
    def rag_explanation_inputs(self):  # noqa: ANN201
        payload = NearbySuggestionRequest(
            question="Which dish should I ask about?",
            allergens=[AllergyTag.PEANUT],
        )
        evidence = [
            HybridSearchResult(
                id="dish-1",
                restaurant_id="alpha",
                restaurant_name="Alpha Cafe",
                dish_name="Tomato Rice Bowl",
                source_type=SourceType.RESTAURANT_WEBSITE,
                source_url="https://example.com/menu",
                raw_text="Tomato Rice Bowl - rice, tomato, greens",
                citation_label="Alpha Cafe menu",
                citation_text="Tomato Rice Bowl - rice, tomato, greens",
            )
        ]
        suggestions = [
            NearbyPlaceSuggestion(
                place=PlaceListItem(
                    id="alpha",
                    name="Alpha Cafe",
                    location=LatLng(lat=38.9, lng=-77.0),
                ),
                confidence=0.6,
                menu_item_count=1,
                evidence=evidence,
                risk_note="Ingredient and preparation details need verification.",
            )
        ]
        return payload, suggestions, evidence, ["Cross-contact handling is unknown."], ["Ask staff about prep."]

    def test_azure_openai_chat_explanation_uses_langchain_trace_config(self) -> None:
        payload, suggestions, evidence, missing, questions = self.rag_explanation_inputs()
        metadata = {
            "restaurant_id": "alpha",
            "source_url": "https://example.com/menu",
            "item_count": 1,
            "retrieval_mode": "hybrid_keyword_semantic",
            "allergens": ["peanut"],
            "safety_gate": "verify_or_abstain",
        }
        env = {
            "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
            "AZURE_OPENAI_API_KEY": "test-key",
            "AZURE_OPENAI_CHAT_DEPLOYMENT": "test-chat",
            "AZURE_OPENAI_CHAT_API_VERSION": "2024-10-21",
        }
        chat_cls = MagicMock()
        langchain_openai = ModuleType("langchain_openai")
        langchain_openai.AzureChatOpenAI = chat_cls
        with patch.dict("os.environ", env, clear=True), patch.dict(
            "sys.modules", {"langchain_openai": langchain_openai}
        ):
            chat_cls.return_value.ainvoke = AsyncMock(
                return_value=SimpleNamespace(content="Possible lower-risk option; needs verification [E1].")
            )
            answer = asyncio.run(
                generate_azure_openai_answer(
                    payload,
                    suggestions,
                    evidence,
                    missing,
                    questions,
                    metadata=metadata,
                )
            )

        self.assertEqual(answer, "Possible lower-risk option; needs verification [E1].")
        config = chat_cls.return_value.ainvoke.await_args.kwargs["config"]
        self.assertEqual(config["run_name"], "AllerNav Azure OpenAI RAG Explanation")
        self.assertEqual(config["tags"], ["allernav", "rag", "azure-openai"])
        self.assertEqual(config["metadata"], metadata)

    def test_rag_explanation_falls_back_to_gemini(self) -> None:
        payload, suggestions, evidence, missing, questions = self.rag_explanation_inputs()
        with patch(
            "allernav_api.rag_service.generate_azure_openai_answer",
            new=AsyncMock(return_value=None),
        ), patch(
            "allernav_api.rag_service.generate_gemini_answer",
            return_value="Needs verification from staff [E1].",
        ) as gemini:
            answer = asyncio.run(generate_nearby_answer(payload, suggestions, evidence, missing, questions))

        self.assertEqual(answer, "Needs verification from staff [E1].")
        gemini.assert_called_once()

    def test_rag_explanation_falls_back_to_deterministic_answer(self) -> None:
        payload, suggestions, evidence, missing, questions = self.rag_explanation_inputs()
        with patch(
            "allernav_api.rag_service.generate_azure_openai_answer",
            new=AsyncMock(return_value=None),
        ), patch("allernav_api.rag_service.generate_gemini_answer", return_value=None):
            answer = asyncio.run(generate_nearby_answer(payload, suggestions, evidence, missing, questions))

        self.assertIn("verification leads", answer)
        self.assertNotIn("safe", answer.lower())

    def test_llm_safety_filter_rejects_safe_language(self) -> None:
        self.assertIsNone(clean_llm_answer("This dish is safe for a peanut allergy."))
        self.assertEqual(clean_llm_answer("This dish needs verification."), "This dish needs verification.")

    def test_health_requires_complete_azure_chat_configuration(self) -> None:
        base = {
            "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
            "AZURE_OPENAI_API_KEY": "test-key",
            "AZURE_OPENAI_CHAT_DEPLOYMENT": "test-chat",
        }
        with patch.dict("os.environ", base, clear=True):
            self.assertFalse(TestClient(app).get("/health").json()["environment"]["azure_openai_chat"])
        with patch.dict("os.environ", {**base, "AZURE_OPENAI_CHAT_API_VERSION": "2024-10-21"}, clear=True):
            self.assertTrue(TestClient(app).get("/health").json()["environment"]["azure_openai_chat"])

    def test_menu_refresh_mode_defaults_and_local_override(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(menu_refresh_mode(), "auto")
        with patch.dict("os.environ", {"MENU_REFRESH_MODE": "local"}, clear=True):
            self.assertEqual(menu_refresh_mode(), "local")

    def test_auto_mode_falls_back_locally_when_durable_persistence_fails(self) -> None:
        fallback_job = MenuRefreshJob(
            id="local-fallback",
            place_id="alpha",
            status="failed",
            message="Local scan finished.",
            created_at="2026-06-29T00:00:00+00:00",
        )
        with patch.dict(
            "os.environ",
            {
                "MENU_REFRESH_MODE": "auto",
                "AZURE_SERVICE_BUS_SEND_CONNECTION_STRING": "configured",
            },
            clear=True,
        ), patch("allernav_api.service.supabase_store.configured", return_value=True), patch(
            "allernav_api.service.supabase_store.save_menu_refresh_job", return_value=False
        ), patch("allernav_api.service._discover_squarespace_image_set", return_value=None), patch(
            "allernav_api.service._create_local_menu_refresh_job", return_value=fallback_job
        ) as local_refresh:
            result = asyncio.run(
                create_menu_refresh_job(
                    "alpha",
                    restaurant_name="Alpha",
                    website_url="https://alpha.example",
                )
            )

        self.assertEqual(result.id, "local-fallback")
        local_refresh.assert_called_once()

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
                kwargs["trace"].append(
                    IngestionTraceStep(
                        id="source_discovery",
                        label="Discover menu sources",
                        status="complete",
                        detail="Found one test menu source.",
                        provider="test",
                    )
                )
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

            with patch("allernav_api.service.ingest_menu_from_website", side_effect=fake_ingest), patch(
                "allernav_api.service.MENU_INDEX_EXECUTOR.submit"
            ) as submit_index, patch("allernav_api.service.index_restaurant_menu") as inline_index:
                client = TestClient(app)
                refresh = client.post(
                    "/api/places/alpha/menu-refresh",
                    params={"restaurant_name": "Alpha", "website_url": "https://example.com/menu"},
                )
                menu = client.get("/api/places/alpha/menu")

            os.environ.pop("ALLERNAV_MENU_DB", None)

        self.assertEqual(refresh.status_code, 202)
        self.assertEqual(refresh.json()["status"], "complete")
        self.assertEqual(refresh.json()["indexing_status"], "pending")
        self.assertEqual(refresh.json()["trace"][0]["id"], "source_discovery")
        self.assertEqual(refresh.json()["trace"][-1]["id"], "search_index")
        self.assertEqual(refresh.json()["trace"][-1]["status"], "pending")
        submit_index.assert_called_once()
        inline_index.assert_not_called()
        self.assertEqual(menu.status_code, 200)
        self.assertEqual(menu.json()["sections"][0]["items"][0]["name"], "Tomato Rice Bowl")

    def test_menu_refresh_queues_squarespace_image_job_when_azure_is_configured(self) -> None:
        menu_html = "".join(
            f'<img data-image="https://images.example/Forever+Thai+Menu+May+2026_Page_{page}.jpg">'
            for page in range(1, 3)
        )
        with patch.dict("os.environ", {"AZURE_SERVICE_BUS_SEND_CONNECTION_STRING": "test-connection"}), patch(
            "allernav_api.service.supabase_store.configured", return_value=True
        ), patch(
            "allernav_api.service.supabase_store.save_menu_refresh_job", return_value=True
        ), patch(
            "allernav_api.service.supabase_store.load_menu_refresh_job", return_value=None
        ), patch(
            "allernav_api.service.fetch_html_url",
            side_effect=lambda url: (
                menu_html
                if url.endswith("/menu")
                else '<a href="/menu">Menu</a>'
                if url.rstrip("/") == "https://www.foreverthaibushwick.com"
                else None
            ),
        ), patch("allernav_api.service.enqueue_menu_refresh") as enqueue:
            client = TestClient(app)
            refresh = client.post(
                "/api/places/forever-thai/menu-refresh",
                params={
                    "restaurant_name": "Forever Thai",
                    "website_url": "https://www.foreverthaibushwick.com/",
                },
            )
            job = client.get(f"/api/menu-refresh-jobs/{refresh.json()['id']}")

        self.assertEqual(refresh.status_code, 202)
        self.assertEqual(refresh.json()["status"], "queued")
        self.assertEqual(refresh.json()["total_documents"], 2)
        self.assertEqual(refresh.json()["menu_version"], "May 2026")
        self.assertEqual(job.status_code, 200)
        enqueue.assert_called_once()
        self.assertEqual(
            enqueue.call_args.args[0].website_url,
            "https://www.foreverthaibushwick.com/menu",
        )

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
        self.assertEqual(restaurant_search_query("I want a french restaurant"), "french restaurants")


if __name__ == "__main__":
    unittest.main()
