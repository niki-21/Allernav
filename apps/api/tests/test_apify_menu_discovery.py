from __future__ import annotations

import os
import unittest

from allernav_api.apify_menu_discovery import (
    build_apify_menu_discovery_input,
    discover_rendered_menu_evidence,
    discover_rendered_menu_urls,
    parse_rendered_menu_discovery,
    parse_rendered_menu_urls,
)


APIFY_RENDERED_PAYLOAD = [
    {
        "url": "https://restaurant.example/",
        "links": [
            {"href": "https://restaurant.example/about", "text": "About"},
            {"href": "https://restaurant.example/menu", "text": "Menu"},
            {"href": "https://restaurant.example/files/dinner.pdf", "text": "Dinner PDF"},
        ],
        "frames": [
            "https://www.toasttab.com/example-restaurant/v3",
            "https://analytics.example/frame",
        ],
        "title": "Restaurant Menu",
        "visibleText": "Dinner Menu\nChicken Bowl - rice, chicken, tomato sauce\nShrimp Salad - greens, shrimp, lemon",
    }
]


class ApifyMenuDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["APIFY_TOKEN"] = "test-token"

    def tearDown(self) -> None:
        os.environ.pop("APIFY_TOKEN", None)
        os.environ.pop("APIFY_MENU_DISCOVERY_ACTOR", None)
        os.environ.pop("APIFY_MENU_DISCOVERY_ENABLED", None)

    def test_builds_playwright_scraper_input_for_rendered_menu_discovery(self) -> None:
        payload = build_apify_menu_discovery_input("https://restaurant.example/")

        self.assertEqual(payload["startUrls"], [{"url": "https://restaurant.example/"}])
        self.assertEqual(payload["linkSelector"], "a[href]")
        self.assertEqual(payload["proxyConfiguration"], {"useApifyProxy": True})
        self.assertIn("pageFunction", payload)
        self.assertIn("page.$$eval('a[href]'", str(payload["pageFunction"]))

    def test_parses_rendered_menu_candidates_from_links_and_frames(self) -> None:
        urls = parse_rendered_menu_urls(APIFY_RENDERED_PAYLOAD)

        self.assertIn("https://restaurant.example/menu", urls)
        self.assertIn("https://restaurant.example/files/dinner.pdf", urls)
        self.assertIn("https://www.toasttab.com/example-restaurant/v3", urls)
        self.assertNotIn("https://restaurant.example/about", urls)
        self.assertNotIn("https://analytics.example/frame", urls)

    def test_parses_rendered_menu_text_pages(self) -> None:
        discovery = parse_rendered_menu_discovery(APIFY_RENDERED_PAYLOAD)

        self.assertEqual(len(discovery.pages), 1)
        self.assertEqual(discovery.pages[0].url, "https://restaurant.example/")
        self.assertIn("Chicken Bowl", discovery.pages[0].visible_text)

    def test_fetches_rendered_candidates_with_expected_actor_endpoint(self) -> None:
        calls = []

        def fake_requester(url, params, body, headers, timeout):  # noqa: ANN001, ANN202
            calls.append((url, params, body, headers, timeout))
            return APIFY_RENDERED_PAYLOAD

        discovery = discover_rendered_menu_evidence("https://restaurant.example/", requester=fake_requester)
        urls = discover_rendered_menu_urls("https://restaurant.example/", requester=fake_requester)

        self.assertEqual(len(discovery.pages), 1)
        self.assertIn("https://restaurant.example/menu", urls)
        self.assertRegex(calls[0][0], r"/actors/apify~playwright-scraper/run-sync-get-dataset-items$")
        self.assertEqual(calls[0][1]["token"], "test-token")
        self.assertEqual(calls[0][2]["startUrls"], [{"url": "https://restaurant.example/"}])
        self.assertEqual(calls[0][3]["Content-Type"], "application/json")


if __name__ == "__main__":
    unittest.main()
