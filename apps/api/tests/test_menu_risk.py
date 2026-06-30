from __future__ import annotations

from allernav_api.menu_risk import classify_menu_item
from allernav_api.models import AllergyTag, MenuItem


def test_sesame_naan_is_avoid_for_sesame() -> None:
    result = classify_menu_item(
        MenuItem(name="Sesame Naan", description="Baked flatbread topped with sesame seeds."),
        [AllergyTag.SESAME],
    )
    assert result.risk_label == "avoid"
    assert result.matched_allergens == [AllergyTag.SESAME]
    assert result.confidence is not None and result.confidence >= 0.78


def test_tandoori_salmon_is_avoid_for_fish() -> None:
    result = classify_menu_item(
        MenuItem(name="Tandoori Salmon", description="Salmon roasted with spices."),
        [AllergyTag.FISH],
    )
    assert result.risk_label == "avoid"
    assert result.matched_allergens == [AllergyTag.FISH]


def test_basmati_rice_with_context_is_possible_lower_risk() -> None:
    result = classify_menu_item(
        MenuItem(name="Basmati Rice", description="Steamed long-grain basmati rice with herbs."),
        [AllergyTag.PEANUT, AllergyTag.SESAME, AllergyTag.FISH],
    )
    assert result.risk_label == "possible_lower_risk"
    assert result.matched_allergens == []
    assert result.confidence is not None and result.confidence > 0.6


def test_vague_item_is_insufficient_info() -> None:
    result = classify_menu_item(MenuItem(name="House Special"), [AllergyTag.PEANUT])
    assert result.risk_label == "insufficient_info"
    assert result.confidence is not None and result.confidence < 0.5


def test_unknown_curry_requires_staff_check() -> None:
    result = classify_menu_item(MenuItem(name="House Curry"), [AllergyTag.PEANUT])
    assert result.risk_label == "needs_check"
