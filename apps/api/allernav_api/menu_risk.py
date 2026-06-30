from __future__ import annotations

from .models import AllergyTag, MenuItem, PlaceMenu
from .risk_engine import ALLERGEN_TERMS, term_matches


PREPARATION_RISK_TERMS = (
    "sauce",
    "marinade",
    "marinated",
    "garnish",
    "fried",
    "fryer",
    "crispy",
    "curry",
    "dressing",
    "chutney",
    "glaze",
    "shared",
    "aioli",
    "pesto",
)


def classify_menu_item(
    item: MenuItem,
    selected_allergens: list[AllergyTag],
    *,
    source_confidence: float | None = None,
) -> MenuItem:
    name = item.name.strip()
    description = (item.description or "").strip()
    text = f"{name} {description}".strip().lower()
    matched = sorted(
        {
            allergen
            for allergen in selected_allergens
            if allergen in item.confirmed_allergens
            or allergen in item.inferred_risks
            or any(term_matches(text, term) for term in ALLERGEN_TERMS[allergen])
        },
        key=lambda allergen: allergen.value,
    )
    source_quality = item.ocr_confidence if item.ocr_confidence is not None else source_confidence
    source_quality = source_quality if source_quality is not None else 0.72
    selected_text = ", ".join(allergen.value.replace("_", " ") for allergen in selected_allergens)
    selected_text = selected_text or "the selected allergens"

    if matched:
        labels = ", ".join(allergen.value.replace("_", " ") for allergen in matched)
        return item.model_copy(
            update={
                "risk_label": "avoid",
                "matched_allergens": matched,
                "risk_reasons": [f"Menu text or structured evidence identifies selected allergen: {labels}."],
                "verification_question": f"Can you confirm whether {name} contains {labels} in any ingredient or garnish?",
                "confidence": round(min(0.98, max(0.78, source_quality + 0.12)), 2),
            }
        )

    preparation_terms = [term for term in PREPARATION_RISK_TERMS if term_matches(text, term)]
    if preparation_terms:
        term_text = ", ".join(preparation_terms[:3])
        confidence = min(0.82, max(0.5, source_quality - 0.05 + min(len(description.split()), 8) * 0.015))
        return item.model_copy(
            update={
                "risk_label": "needs_check",
                "matched_allergens": [],
                "risk_reasons": [f"Preparation wording needs staff verification: {term_text}."],
                "verification_question": (
                    f"Does the {term_text} used for {name} contain {selected_text}, or share preparation equipment?"
                ),
                "confidence": round(confidence, 2),
            }
        )

    description_words = [word for word in description.split() if any(character.isalpha() for character in word)]
    if len(description_words) < 3 or len(description) < 12:
        return item.model_copy(
            update={
                "risk_label": "insufficient_info",
                "matched_allergens": [],
                "risk_reasons": ["The menu does not provide enough ingredient or preparation detail."],
                "verification_question": f"What ingredients and preparation steps are used for {name}?",
                "confidence": round(min(0.48, max(0.22, source_quality - 0.35)), 2),
            }
        )

    context_score = min(0.14, len(description_words) * 0.012)
    return item.model_copy(
        update={
            "risk_label": "possible_lower_risk",
            "matched_allergens": [],
            "risk_reasons": ["No selected allergen terms were found in the available ingredient description."],
            "verification_question": (
                f"Can you verify that {name} contains no {selected_text} and is prepared without shared-contact risk?"
            ),
            "confidence": round(min(0.9, max(0.62, source_quality - 0.02 + context_score)), 2),
        }
    )


def classify_place_menu(menu: PlaceMenu, selected_allergens: list[AllergyTag]) -> PlaceMenu:
    if not selected_allergens:
        return menu
    return menu.model_copy(
        update={
            "sections": [
                section.model_copy(
                    update={
                        "items": [
                            classify_menu_item(
                                item,
                                selected_allergens,
                                source_confidence=menu.extraction_confidence,
                            )
                            for item in section.items
                        ]
                    }
                )
                for section in menu.sections
            ]
        }
    )
