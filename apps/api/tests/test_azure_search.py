from __future__ import annotations

import os
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from allernav_api.azure_search import (
    build_hybrid_query,
    build_index_documents,
    detect_allergens_in_text,
    freshness_adjusted_confidence,
    hybrid_search_menu,
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
