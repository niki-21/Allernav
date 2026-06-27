from __future__ import annotations

import unittest
from unittest.mock import patch

from allernav_api.document_intelligence import AzureDocumentIntelligenceClient


class DocumentIntelligenceTests(unittest.TestCase):
    def test_layout_analysis_requests_markdown_output(self) -> None:
        client = AzureDocumentIntelligenceClient(
            endpoint="https://documents.example.test",
            api_key="test-key",
        )
        captured_urls: list[str] = []

        def fake_post(url: str, _payload: bytes) -> str:
            captured_urls.append(url)
            return "https://documents.example.test/result"

        result_payload = {
            "analyzeResult": {
                "content": "# Dinner\n\nTomato Rice Bowl | 18",
                "pages": [{"words": [{"content": "Dinner", "confidence": 0.98}]}],
            }
        }

        with patch.object(client, "_post_analyze", side_effect=fake_post), patch.object(
            client,
            "_poll_result",
            return_value=result_payload,
        ):
            extraction = client.extract_from_url("https://restaurant.example/menu.pdf")

        self.assertIsNotNone(extraction)
        self.assertIn("outputContentFormat=markdown", captured_urls[0])
        self.assertEqual(extraction.page_count, 1)
        self.assertEqual(extraction.confidence, 0.98)


if __name__ == "__main__":
    unittest.main()
