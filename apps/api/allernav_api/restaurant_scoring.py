from __future__ import annotations

from dataclasses import dataclass

from .menu_risk import classify_menu_item
from .models import AllergyTag, MenuSource


@dataclass(frozen=True)
class RestaurantFitScore:
    score: int
    label: str
    menu_item_count: int
    avoid_count: int
    needs_check_count: int
    possible_lower_risk_count: int
    insufficient_info_count: int
    evidence_quality: float
    reason: str
    next_action: str


def score_restaurant_menu(
    source: MenuSource | None,
    selected_allergens: list[AllergyTag],
) -> RestaurantFitScore:
    if source is None:
        return RestaurantFitScore(
            score=20,
            label="Scan needed",
            menu_item_count=0,
            avoid_count=0,
            needs_check_count=0,
            possible_lower_risk_count=0,
            insufficient_info_count=0,
            evidence_quality=0,
            reason="No scanned menu evidence is available yet.",
            next_action="Scan this menu before comparing allergy fit.",
        )

    source_confidence = source.extraction_confidence
    if source_confidence is None:
        source_confidence = source.reliability
    classified = [
        classify_menu_item(item, selected_allergens, source_confidence=source_confidence)
        for section in source.sections
        for item in section.items
    ]
    item_count = len(classified)
    if item_count == 0:
        return RestaurantFitScore(
            score=20,
            label="Scan needed",
            menu_item_count=0,
            avoid_count=0,
            needs_check_count=0,
            possible_lower_risk_count=0,
            insufficient_info_count=0,
            evidence_quality=0,
            reason="The scan did not produce reliable dish-level evidence.",
            next_action="Run another menu scan or inspect the official menu source.",
        )

    counts = {
        "avoid": sum(item.risk_label == "avoid" for item in classified),
        "needs_check": sum(item.risk_label == "needs_check" for item in classified),
        "possible_lower_risk": sum(item.risk_label == "possible_lower_risk" for item in classified),
        "insufficient_info": sum(item.risk_label == "insufficient_info" for item in classified),
    }
    described_ratio = sum(bool((item.description or "").strip()) for item in classified) / item_count
    evidence_quality = min(1.0, max(0.0, source_confidence * 0.65 + described_ratio * 0.35))
    avoid_ratio = counts["avoid"] / item_count
    uncertainty_ratio = (counts["needs_check"] + counts["insufficient_info"]) / item_count
    possible_ratio = counts["possible_lower_risk"] / item_count
    score = round(
        50
        + 25 * possible_ratio
        + 15 * evidence_quality
        - 30 * avoid_ratio
        - 15 * uncertainty_ratio
    )
    score = max(0, min(100, score))

    if avoid_ratio >= 0.3 or score < 40:
        label = "Higher concern"
    elif score >= 65 and counts["possible_lower_risk"] > 0:
        label = "Best current candidate"
    else:
        label = "Needs verification"

    if counts["avoid"]:
        reason = (
            f"{counts['avoid']} item{'s' if counts['avoid'] != 1 else ''} match selected allergens; "
            f"{counts['possible_lower_risk']} possible lower-risk item"
            f"{'s' if counts['possible_lower_risk'] != 1 else ''} remain to verify."
        )
    elif counts["possible_lower_risk"]:
        reason = (
            f"{counts['possible_lower_risk']} possible lower-risk item"
            f"{'s' if counts['possible_lower_risk'] != 1 else ''} have source-backed descriptions."
        )
    else:
        reason = "The menu is scanned, but its items still need ingredient or preparation checks."

    return RestaurantFitScore(
        score=score,
        label=label,
        menu_item_count=item_count,
        avoid_count=counts["avoid"],
        needs_check_count=counts["needs_check"],
        possible_lower_risk_count=counts["possible_lower_risk"],
        insufficient_info_count=counts["insufficient_info"],
        evidence_quality=round(evidence_quality, 2),
        reason=reason,
        next_action="Ask staff to verify the highlighted dishes and shared preparation controls.",
    )
