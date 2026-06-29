from __future__ import annotations

import unittest
from unittest.mock import patch

from allernav_api.web_menu_discovery import (
    build_menu_search_queries,
    discover_web_menu_candidates,
    parse_google_search_candidates,
    parse_serpapi_candidates,
)


class WebMenuDiscoveryTests(unittest.TestCase):
    def test_builds_name_site_and_location_queries(self) -> None:
        queries = build_menu_search_queries(
            restaurant_name="Maison Provence",
            website_url="https://www.maison.example/",
            address="Brooklyn, NY",
        )

        self.assertEqual(queries[0], "site:maison.example (menu OR pdf OR jpg)")
        self.assertIn('site:maison.example/items/ "Maison Provence"', queries)
        self.assertIn('"Maison Provence" menu pdf', queries)
        self.assertIn('"Maison Provence" food menu Brooklyn, NY', queries)

    def test_parses_google_results_and_image_metadata(self) -> None:
        candidates = parse_google_search_candidates(
            {
                "items": [
                    {
                        "title": "Dinner Menu",
                        "link": "https://restaurant.example/menu",
                        "snippet": "Menu",
                        "pagemap": {"cse_image": [{"src": "https://restaurant.example/menu.jpg"}]},
                    }
                ]
            }
        )

        self.assertEqual(candidates[0].url, "https://restaurant.example/menu")
        self.assertEqual(candidates[1].url, "https://restaurant.example/menu.jpg")
        self.assertEqual(candidates[1].title, "Dinner Menu")

    def test_parses_serpapi_organic_and_image_results(self) -> None:
        candidates = parse_serpapi_candidates(
            {
                "organic_results": [{"title": "Menu PDF", "link": "https://restaurant.example/menu.pdf"}],
                "images_results": [{"title": "Menu Photo", "original": "https://restaurant.example/photo-menu.jpeg"}],
            }
        )

        self.assertEqual([candidate.url for candidate in candidates], ["https://restaurant.example/menu.pdf", "https://restaurant.example/photo-menu.jpeg"])

    def test_discovers_candidates_with_google_programmable_search(self) -> None:
        calls: list[str] = []

        def fake_requester(url: str, _timeout: float):  # noqa: ANN202
            calls.append(url)
            return {
                "items": [
                    {"title": "About", "link": "https://restaurant.example/about"},
                    {"title": "Menu PDF", "link": "https://restaurant.example/menu.pdf"},
                ]
            }

        with patch.dict(
            "os.environ",
            {
                "GOOGLE_SEARCH_API_KEY": "search-key",
                "GOOGLE_SEARCH_ENGINE_ID": "engine-id",
            },
        ):
            candidates = discover_web_menu_candidates(
                restaurant_name="Maison Provence",
                website_url="https://restaurant.example/",
                requester=fake_requester,
            )

        self.assertTrue(calls)
        self.assertEqual([candidate.url for candidate in candidates], ["https://restaurant.example/menu.pdf"])

    def test_keeps_official_popmenu_item_pages_as_discovery_candidates(self) -> None:
        def fake_requester(_url: str, _timeout: float):  # noqa: ANN202
            return {
                "items": [
                    {"title": "Truffle Burger", "link": "https://restaurant.example/items/truffle-burger"},
                ]
            }

        with patch.dict(
            "os.environ",
            {"GOOGLE_SEARCH_API_KEY": "search-key", "GOOGLE_SEARCH_ENGINE_ID": "engine-id"},
        ):
            candidates = discover_web_menu_candidates(
                restaurant_name="Restaurant",
                website_url="https://restaurant.example/",
                requester=fake_requester,
            )

        self.assertEqual(candidates[0].url, "https://restaurant.example/items/truffle-burger")

    def test_records_safe_provider_diagnostics_without_request_url(self) -> None:
        diagnostics: list[str] = []

        def failing_requester(_url: str, _timeout: float):  # noqa: ANN202
            from urllib.error import HTTPError

            raise HTTPError("https://redacted.invalid", 403, "Forbidden", {}, None)

        with patch.dict(
            "os.environ",
            {"GOOGLE_SEARCH_API_KEY": "secret-key", "GOOGLE_SEARCH_ENGINE_ID": "engine-id"},
        ):
            discover_web_menu_candidates(
                restaurant_name="Restaurant",
                website_url="https://restaurant.example/",
                requester=failing_requester,
                diagnostics=diagnostics,
            )

        self.assertEqual(diagnostics, ["Google Programmable Search returned HTTP 403."])
        self.assertNotIn("secret-key", " ".join(diagnostics))


if __name__ == "__main__":
    unittest.main()
