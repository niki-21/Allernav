from __future__ import annotations

from .models import (
    AllergyTag,
    EvidenceFragment,
    MenuItem,
    MenuSection,
    MenuSource,
    RestaurantContext,
    SourceType,
)


FIXTURE_CONTEXTS: dict[str, RestaurantContext] = {
    "demo-bagel": RestaurantContext(
        restaurant_id="demo-bagel",
        restaurant_name="Demo Bagel Cafe",
        menu_sources=[
            MenuSource(
                source_type=SourceType.FIXTURE,
                source_url="fixture://demo-bagel/menu",
                reliability=0.82,
                sections=[
                    MenuSection(
                        title="Bagels and spreads",
                        items=[
                            MenuItem(
                                name="Sesame Bagel with Cream Cheese",
                                description="Sesame bagel, wheat flour, plain cream cheese.",
                            ),
                            MenuItem(
                                name="Plain Bagel",
                                description="Wheat flour bagel served toasted with optional spreads.",
                            ),
                            MenuItem(
                                name="Fruit Cup",
                                description="Seasonal fruit packed cold.",
                            ),
                        ],
                    )
                ],
            )
        ],
    ),
    "demo-pasta": RestaurantContext(
        restaurant_id="demo-pasta",
        restaurant_name="Demo Pasta House",
        menu_sources=[
            MenuSource(
                source_type=SourceType.FIXTURE,
                source_url="fixture://demo-pasta/menu",
                reliability=0.84,
                sections=[
                    MenuSection(
                        title="Pastas",
                        items=[
                            MenuItem(
                                name="Chicken Alfredo",
                                description="Pasta with cream sauce, butter, and parmesan.",
                            ),
                            MenuItem(
                                name="Pesto Primavera",
                                description="Pasta with basil pesto, parmesan, and seasonal vegetables.",
                            ),
                            MenuItem(
                                name="Tomato Basil Bowl",
                                description="Rice, tomato basil sauce, roasted vegetables.",
                            ),
                        ],
                    )
                ],
            )
        ],
    ),
    "demo-review-only": RestaurantContext(
        restaurant_id="demo-review-only",
        restaurant_name="Demo Review Only",
        menu_sources=[
            MenuSource(
                source_type=SourceType.REVIEW,
                source_url="fixture://demo-review-only/reviews",
                reliability=0.35,
                raw_text="Grilled Chicken Bowl - reviewer said it tasted simple",
            )
        ],
        review_evidence=[
            EvidenceFragment(
                id="review-only-1",
                source_type=SourceType.REVIEW,
                text="A reviewer said the staff was careful with allergies, but no menu ingredients were listed.",
                matched_allergens=[AllergyTag.PEANUT],
                reliability=0.35,
            )
        ],
    ),
}


def get_fixture_context(identifier: str | None, name: str | None = None) -> RestaurantContext | None:
    if identifier and identifier in FIXTURE_CONTEXTS:
        return FIXTURE_CONTEXTS[identifier]

    normalized_name = (name or "").lower()
    for context in FIXTURE_CONTEXTS.values():
        if context.restaurant_name and context.restaurant_name.lower() in normalized_name:
            return context
    return None
