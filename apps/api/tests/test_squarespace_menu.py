from __future__ import annotations

import unittest

from allernav_api.squarespace_menu import discover_squarespace_menu_images


def image_url(identifier: str, filename: str) -> str:
    return f"https://images.squarespace-cdn.com/content/v1/site/{identifier}/{filename}"


class SquarespaceMenuTests(unittest.TestCase):
    def test_selects_newest_complete_numbered_menu_edition(self) -> None:
        old = [image_url(f"old-{page}", f"FOREVER+MENU+LETTER+SIZE+{page}.jpg") for page in range(1, 4)]
        current = [
            image_url(f"new-{page}", f"Forever+Thai+Menu+May+2026_Page_{page}.jpg")
            for page in range(1, 7)
        ]
        html = "".join(f'<img data-image="{url}" src="{url}?format=100w">' for url in [*old, *reversed(current)])

        result = discover_squarespace_menu_images(html, "https://www.foreverthaibushwick.com/menu")

        self.assertIsNotNone(result)
        self.assertEqual(result.version, "May 2026")
        self.assertEqual(result.document_urls, current)

    def test_reads_highest_srcset_candidate_when_data_attributes_are_absent(self) -> None:
        base = image_url("page", "Dinner+Menu+Page+1.jpg")
        html = f'<img alt="Dinner menu" srcset="{base}?format=300w 300w, {base}?format=2500w 2500w">'

        result = discover_squarespace_menu_images(html, "https://restaurant.example/menu")

        self.assertIsNotNone(result)
        self.assertEqual(result.document_urls, [base])

    def test_ignores_food_photos_without_numbered_menu_signal(self) -> None:
        html = '<img src="https://images.example/food.jpg" alt="Menu food photo">'

        self.assertIsNone(discover_squarespace_menu_images(html, "https://restaurant.example/menu"))


if __name__ == "__main__":
    unittest.main()
