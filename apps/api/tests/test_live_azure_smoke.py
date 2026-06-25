from __future__ import annotations

import os
import unittest

from allernav_api.azure_openai_embeddings import AzureOpenAIEmbeddingClient
from allernav_api.azure_search import AzureSearchClient, build_hybrid_query
from allernav_api.models import HybridSearchRequest


LIVE_CLOUD_ENABLED = os.getenv("ALLERNAV_LIVE_CLOUD_TESTS", "").lower() in {"1", "true", "yes"}


@unittest.skipUnless(LIVE_CLOUD_ENABLED, "Set ALLERNAV_LIVE_CLOUD_TESTS=true to run live Azure smoke tests.")
class LiveAzureSmokeTests(unittest.TestCase):
    def test_embedding_dimension_matches_search_index(self) -> None:
        vector = AzureOpenAIEmbeddingClient().embed_text("AllerNav embedding smoke test")

        self.assertEqual(len(vector), 1536)

    def test_hybrid_query_can_reach_azure_search(self) -> None:
        response = AzureSearchClient().hybrid_search(HybridSearchRequest(query="peanut", top=1))

        self.assertEqual(response.query, "peanut")

    def test_query_body_includes_vector_when_embeddings_configured(self) -> None:
        body = build_hybrid_query(HybridSearchRequest(query="sesame tahini", top=1))

        self.assertIn("vectorQueries", body)


if __name__ == "__main__":
    unittest.main()
