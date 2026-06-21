from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from allernav_api.apify_reviews import (
    fetch_apify_reviews,
    load_cached_reviews,
    load_or_fetch_reviews,
    parse_apify_reviews,
)


APIFY_PAYLOAD = [
    {
        "name": "Alpha Cafe",
        "place_id": "alpha",
        "reviews": [
            {
                "reviewId": "review-1",
                "authorName": "Pat",
                "text": "I have a sesame allergy and they warned me about cross-contact.",
                "rating": 2,
                "timestamp": 1780000000,
                "reviewUrl": "https://example.com/review/1",
            },
            {
                "reviewId": "review-2",
                "reviewerName": "Rae",
                "reviewText": "Great patio.",
                "stars": "5",
                "publishedAtDate": "06/01/2026 15:30:00",
            },
            {
                "reviewId": "empty",
                "text": "",
            },
        ],
    }
]


class ApifyReviewsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "reviews.sqlite"
        os.environ["APIFY_TOKEN"] = "test-token"
        os.environ["APIFY_REVIEWS_LIMIT"] = "25"
        os.environ["APIFY_REVIEWS_SORT"] = "newest"
        os.environ["APIFY_LANGUAGE"] = "en"
        os.environ["APIFY_REGION"] = "US"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()
        for key in [
            "APIFY_TOKEN",
            "APIFY_REVIEWS_LIMIT",
            "APIFY_REVIEWS_SORT",
            "APIFY_LANGUAGE",
            "APIFY_REGION",
        ]:
            os.environ.pop(key, None)

    def test_parses_apify_review_payload(self) -> None:
        reviews = parse_apify_reviews(APIFY_PAYLOAD)

        self.assertEqual(len(reviews), 2)
        self.assertEqual(reviews[0].review_id, "review-1")
        self.assertEqual(reviews[0].author_name, "Pat")
        self.assertIn("sesame allergy", reviews[0].text)
        self.assertEqual(reviews[0].rating, 2.0)
        self.assertRegex(reviews[0].publish_time or "", r"2026")

    def test_fetches_with_expected_api_params_and_caches_result(self) -> None:
        calls = []

        def fake_requester(url, params, body, headers, timeout):  # noqa: ANN001, ANN202
            calls.append((url, params, body, headers, timeout))
            return APIFY_PAYLOAD

        reviews = fetch_apify_reviews("alpha-place-id", requester=fake_requester, db_path=self.db_path)
        cached = load_cached_reviews("alpha-place-id", db_path=self.db_path)

        self.assertEqual(len(reviews), 2)
        self.assertEqual(len(cached), 2)
        self.assertRegex(calls[0][0], r"/actors/kaix~google-maps-reviews-scraper/run-sync-get-dataset-items$")
        self.assertEqual(calls[0][1]["token"], "test-token")
        self.assertEqual(calls[0][2]["urls"], ["https://www.google.com/maps/place/?q=place_id:alpha-place-id"])
        self.assertEqual(calls[0][2]["maxReviews"], 25)
        self.assertEqual(calls[0][2]["sort"], "newest")
        self.assertEqual(calls[0][2]["language"], "en")
        self.assertEqual(calls[0][2]["region"], "US")
        self.assertEqual(calls[0][3]["Content-Type"], "application/json")

    def test_load_or_fetch_uses_cached_reviews_before_api(self) -> None:
        fetch_apify_reviews("alpha-place-id", requester=lambda *_args: APIFY_PAYLOAD, db_path=self.db_path)

        def failing_requester(*_args):  # noqa: ANN202
            raise AssertionError("API should not be called when cache is fresh")

        reviews = load_or_fetch_reviews("alpha-place-id", requester=failing_requester, db_path=self.db_path)

        self.assertEqual(len(reviews), 2)


if __name__ == "__main__":
    unittest.main()
