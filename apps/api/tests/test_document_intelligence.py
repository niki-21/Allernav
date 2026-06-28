from __future__ import annotations

import unittest
from unittest.mock import patch

from allernav_api.document_intelligence import AzureDocumentIntelligenceClient, safe_public_document_url


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

    def test_downloads_and_submits_bytes_when_url_source_is_rejected(self) -> None:
        client = AzureDocumentIntelligenceClient(endpoint="https://documents.example.test", api_key="test-key")
        calls: list[tuple[str, bytes, str]] = []

        def fake_post(url: str, payload: bytes, *, content_type: str = "application/json") -> str | None:
            calls.append((url, payload, content_type))
            return None if content_type == "application/json" else "https://documents.example.test/result"

        result_payload = {
            "analyzeResult": {
                "content": "CHICKEN SATAY\nThai chicken with Peanut Sauce",
                "pages": [{"words": [{"content": "Chicken", "confidence": 0.91}]}],
            }
        }
        with patch.object(client, "_post_analyze", side_effect=fake_post), patch.object(
            client,
            "_download_document",
            return_value=(b"jpeg-bytes", "image/jpeg"),
        ), patch.object(client, "_poll_result", return_value=result_payload):
            extraction = client.extract_from_url("https://images.example/menu.jpg")

        self.assertIsNotNone(extraction)
        self.assertEqual(calls[0][2], "application/json")
        self.assertEqual(calls[1][1:], (b"jpeg-bytes", "image/jpeg"))

    def test_byte_fallback_rejects_private_and_non_https_urls(self) -> None:
        self.assertFalse(safe_public_document_url("http://images.example/menu.jpg"))
        self.assertFalse(safe_public_document_url("https://127.0.0.1/menu.jpg"))


if __name__ == "__main__":
    unittest.main()
