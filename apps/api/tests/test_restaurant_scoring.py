from allernav_api.models import AllergyTag, MenuItem, MenuSection, MenuSource, SourceType
from allernav_api.restaurant_scoring import score_restaurant_menu


def menu_source(items: list[MenuItem]) -> MenuSource:
    return MenuSource(
        source_type=SourceType.RESTAURANT_WEBSITE,
        reliability=0.85,
        sections=[MenuSection(title="Menu", items=items)],
    )


def test_restaurant_score_penalizes_selected_allergen_matches() -> None:
    lower_risk = score_restaurant_menu(
        menu_source([MenuItem(name="Basmati Rice", description="Steamed rice with herbs and lemon")]),
        [AllergyTag.SESAME, AllergyTag.FISH],
    )
    concern = score_restaurant_menu(
        menu_source([MenuItem(name="Sesame Naan", description="Naan topped with sesame seeds")]),
        [AllergyTag.SESAME, AllergyTag.FISH],
    )

    assert lower_risk.possible_lower_risk_count == 1
    assert concern.avoid_count == 1
    assert concern.score < lower_risk.score


def test_restaurant_score_does_not_reward_menu_size_alone() -> None:
    concise = score_restaurant_menu(
        menu_source([MenuItem(name="Herb Rice", description="Steamed rice with herbs and lemon")]),
        [AllergyTag.PEANUT],
    )
    vague = score_restaurant_menu(
        menu_source([MenuItem(name=f"Dish {index}") for index in range(20)]),
        [AllergyTag.PEANUT],
    )

    assert concise.score > vague.score
    assert vague.insufficient_info_count == 20


def test_scan_needed_score_is_capped_and_not_recommended() -> None:
    score = score_restaurant_menu(None, [AllergyTag.PEANUT])
    assert score.score <= 20
    assert score.label == "Scan needed"
