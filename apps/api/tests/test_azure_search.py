from __future__ import annotations

import os
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from allernav_api.azure_search import (
    AzureSearchClient,
    build_hybrid_query,
    build_index_documents,
    detect_allergens_in_text,
    freshness_adjusted_confidence,
    hybrid_search_menu,
    retrieval_mode_from_query,
)
from allernav_api.menu_ingestion import save_menu_source
from allernav_api.models import AllergyTag, HybridSearchRequest, MenuItem, MenuSection, MenuSource, SourceType


class AzureSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "menus.sqlite"
        os.environ["ALLERNAV_MENU_DB"] = str(self.db_path)
        os.environ.pop("AZURE_SEARCH_ENDPOINT", None)
        os.environ.pop("AZURE_SEARCH_API_KEY", None)
        os.environ.pop("AZURE_SEARCH_INDEX_NAME", None)
        os.environ.pop("AZURE_OPENAI_ENDPOINT", None)
        os.environ.pop("AZURE_OPENAI_API_KEY", None)
        os.environ.pop("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", None)
        os.environ.pop("AZURE_OPENAI_API_VERSION", None)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()
        os.environ.pop("ALLERNAV_MENU_DB", None)
        os.environ.pop("AZURE_OPENAI_EMBEDDING_BATCH_SIZE", None)

    def test_build_index_documents_contains_required_fields(self) -> None:
        source = MenuSource(
            source_type=SourceType.OFFICIAL_MENU,
            source_url="https://example.com/menu.pdf",
            source_timestamp=datetime.now(UTC).isoformat(),
            reliability=0.84,
            sections=[
                MenuSection(
                    title="Dinner",
                    items=[MenuItem(name="Peanut Noodles", description="Wheat noodles, peanut sauce, sesame")],
                )
            ],
        )

        document = build_index_documents(restaurant_id="alpha", restaurant_name="Alpha", source=source)[0]

        self.assertEqual(document["restaurant_id"], "alpha")
        self.assertEqual(document["restaurant_name"], "Alpha")
        self.assertEqual(document["dish_name"], "Peanut Noodles")
        self.assertEqual(document["menu_section"], "Dinner")
        self.assertIn("peanut", document["allergens"])
        self.assertIn("sesame", document["allergens"])
        self.assertIn("embedding", document)

    def test_build_index_documents_reuses_client_and_batches_embeddings(self) -> None:
        os.environ["AZURE_OPENAI_ENDPOINT"] = "https://example.openai.azure.com"
        os.environ["AZURE_OPENAI_API_KEY"] = "test-key"
        os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"] = "text-embedding-3-small"
        os.environ["AZURE_OPENAI_EMBEDDING_BATCH_SIZE"] = "2"
        calls: list[list[str]] = []

        class FakeEmbeddingClient:
            def embed_texts(self, texts: list[str]) -> list[list[float]]:
                calls.append(texts)
                return [[float(len(text))] for text in texts]

        source = MenuSource(
            source_type=SourceType.OFFICIAL_MENU,
            source_url="https://example.com/menu",
            sections=[
                MenuSection(
                    title="Dinner",
                    items=[MenuItem(name=f"Dish {index}", description="Rice and vegetables") for index in range(5)],
                )
            ],
        )

        fake_client = FakeEmbeddingClient()
        with patch("allernav_api.azure_search.AzureOpenAIEmbeddingClient", return_value=fake_client) as client_type:
            documents = build_index_documents(
                restaurant_id="alpha",
                restaurant_name="Alpha",
                source=source,
            )

        client_type.assert_called_once_with()
        self.assertEqual([len(batch) for batch in calls], [2, 2, 1])
        self.assertTrue(all(document["embedding"] for document in documents))

    def test_exact_allergen_keyword_detection_finds_menu_terms(self) -> None:
        detected = detect_allergens_in_text("tahini cream sauce with soy sauce and peanut garnish")

        self.assertIn(AllergyTag.SESAME, detected)
        self.assertIn(AllergyTag.DAIRY, detected)
        self.assertIn(AllergyTag.SOY, detected)
        self.assertIn(AllergyTag.PEANUT, detected)

    def test_hybrid_query_combines_keyword_filter_and_vector(self) -> None:
        query = build_hybrid_query(
            HybridSearchRequest(
                query="lower risk for dairy",
                allergens=[AllergyTag.DAIRY],
                restaurant_id="alpha",
                source_types=[SourceType.OFFICIAL_MENU],
                vector=[0.1, 0.2],
                top=3,
            )
        )

        self.assertIn("cream", query["search"])
        self.assertIn("restaurant_id eq 'alpha'", query["filter"])
        self.assertIn("source_type eq 'official_menu'", query["filter"])
        self.assertEqual(query["vectorQueries"][0]["fields"], "embedding")
        self.assertEqual(retrieval_mode_from_query(query), "hybrid")

    def test_hybrid_query_auto_embeds_and_reports_hybrid_mode(self) -> None:
        os.environ["AZURE_OPENAI_ENDPOINT"] = "https://example.openai.azure.com"
        os.environ["AZURE_OPENAI_API_KEY"] = "test-key"
        os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"] = "text-embedding-3-small"

        with patch("allernav_api.azure_search.AzureOpenAIEmbeddingClient.embed_text", return_value=[0.1, 0.2]):
            query = build_hybrid_query(HybridSearchRequest(query="sesame tahini", top=2))

        self.assertIn("vectorQueries", query)
        self.assertEqual(retrieval_mode_from_query(query), "hybrid")

    def test_azure_results_report_hybrid_when_vector_is_generated_internally(self) -> None:
        os.environ["AZURE_OPENAI_ENDPOINT"] = "https://example.openai.azure.com"
        os.environ["AZURE_OPENAI_API_KEY"] = "test-key"
        os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"] = "text-embedding-3-small"

        with (
            patch("allernav_api.azure_search.AzureOpenAIEmbeddingClient.embed_text", return_value=[0.1, 0.2]),
            patch.object(
                AzureSearchClient,
                "_request_json",
                return_value={
                    "value": [
                        {
                            "id": "doc-1",
                            "restaurant_id": "alpha",
                            "dish_name": "Tahini Bowl",
                            "source_type": "official_menu",
                            "raw_text": "Tahini Bowl: rice, tahini, tomato",
                        }
                    ]
                },
            ),
        ):
            response = AzureSearchClient(
                endpoint="https://example.search.windows.net",
                api_key="key",
                index_name="idx",
            ).hybrid_search(HybridSearchRequest(query="sesame option"))

        self.assertEqual(response.results[0].retrieval_mode, "hybrid")
        self.assertIn("Tahini Bowl", response.results[0].citation_label)

    def test_local_vector_only_result_cannot_support_low_risk(self) -> None:
        save_menu_source(
            restaurant_id="vector-place",
            restaurant_name="Vector Place",
            source=MenuSource(
                source_type=SourceType.OFFICIAL_MENU,
                source_url="https://example.com/menu",
                reliability=0.8,
                sections=[
                    MenuSection(
                        title="Bowls",
                        items=[MenuItem(name="Rice Bowl", description="Rice, cucumber, tomato")],
                    )
                ],
            ),
            db_path=self.db_path,
        )

        response = hybrid_search_menu(
            HybridSearchRequest(
                query="semantic lower risk",
                restaurant_id="vector-place",
                vector=[0.1, 0.2, 0.3],
            )
        )

        self.assertEqual(response.results[0].retrieval_mode, "vector")
        self.assertFalse(response.results[0].can_support_low_risk)

    def test_local_semantic_result_is_retrieved_but_not_low_risk_proof(self) -> None:
        save_menu_source(
            restaurant_id="semantic-place",
            restaurant_name="Semantic Place",
            source=MenuSource(
                source_type=SourceType.OFFICIAL_MENU,
                source_url="https://example.com/menu",
                reliability=0.8,
                sections=[
                    MenuSection(
                        title="Mains",
                        items=[MenuItem(name="Roasted Vegetable Rice Bowl", description="Rice, squash, herbs")],
                    )
                ],
            ),
            db_path=self.db_path,
        )

        response = hybrid_search_menu(
            HybridSearchRequest(
                query="suggest a lower risk dinner option",
                restaurant_id="semantic-place",
            )
        )

        self.assertEqual(response.results[0].retrieval_mode, "semantic")
        self.assertFalse(response.results[0].can_support_low_risk)

    def test_stale_source_metadata_lowers_confidence(self) -> None:
        fresh = freshness_adjusted_confidence(datetime.now(UTC).isoformat(), 0.8)
        stale = freshness_adjusted_confidence("2024-01-01T00:00:00+00:00", 0.8)

        self.assertEqual(fresh, 0.8)
        self.assertLess(stale, fresh)


if __name__ == "__main__":
    unittest.main()
