from __future__ import annotations

import unittest

from allernav_api.azure_search import detect_allergens_in_text, document_to_result
from allernav_api.models import AllergyProfile, AllergyTag, MenuItem, MenuSection, MenuSource, RestaurantContext, SourceType
from allernav_api.risk_engine import analyze_restaurant_context


class RagEvalTests(unittest.TestCase):
    def test_arabic_allergen_aliases_match_original_text(self) -> None:
        detected = detect_allergens_in_text("طبق دجاج مع طحينة وسمسم وصلصة الصويا")

        self.assertIn(AllergyTag.SESAME, detected)
        self.assertIn(AllergyTag.SOY, detected)

    def test_citation_fields_are_source_backed(self) -> None:
        result = document_to_result(
            {
                "id": "doc-1",
                "restaurant_id": "alpha",
                "dish_name": "Tahini Chicken",
                "menu_section": "Dinner",
                "source_type": "official_menu",
                "raw_text": "Tahini Chicken: grilled chicken, tahini sauce, herbs.",
                "confidence": 0.82,
            },
            [AllergyTag.SESAME],
            "hybrid",
        )

        self.assertEqual(result.citation_label, "official menu: Dinner / Tahini Chicken")
        self.assertIn("tahini sauce", result.citation_text)

    def test_safety_gate_abstains_on_missing_ingredient_context(self) -> None:
        result = analyze_restaurant_context(
            RestaurantContext(
                restaurant_id="alpha",
                menu_sources=[
                    MenuSource(
                        source_type=SourceType.OFFICIAL_MENU,
                        source_url="https://example.com/menu",
                        sections=[MenuSection(title="Dinner", items=[MenuItem(name="Chef Special")])],
                    )
                ],
            ),
            AllergyProfile(allergens=[AllergyTag.PEANUT]),
        )

        self.assertEqual(result.recommended_action.value, "insufficient_evidence")
        self.assertTrue(result.missing_information)


if __name__ == "__main__":
    unittest.main()
