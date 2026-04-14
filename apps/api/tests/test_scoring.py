from __future__ import annotations

import unittest

from allernav_api.models import AllergyTag, Verdict
from allernav_api.scoring import analyze_place


class ScoringTests(unittest.TestCase):
    def test_direct_allergen_accommodation_scores_well(self) -> None:
        place = {
            "rating": 4.6,
            "reviews": [
                {
                    "review_id": "1",
                    "rating": 5,
                    "text": "I have a peanut allergy and felt safe here. The staff understood and double checked everything.",
                    "publish_time": "2026-01-10T12:00:00Z",
                }
            ],
        }

        summary, evidence, _ = analyze_place(place, [AllergyTag.PEANUT])

        self.assertGreaterEqual(summary.score, 70)
        self.assertEqual(summary.verdict, Verdict.GOOD_FIT)
        self.assertGreaterEqual(summary.evidence_count, 2)
        self.assertTrue(any(item.matched_allergens for item in evidence))

    def test_false_positive_phrase_stays_negative(self) -> None:
        place = {
            "rating": 2.8,
            "reviews": [
                {
                    "review_id": "1",
                    "rating": 2,
                    "text": "Definitely not allergy friendly. The staff didn't understand my dairy allergy at all.",
                    "publish_time": "2025-12-10T12:00:00Z",
                }
            ],
        }

        summary, evidence, _ = analyze_place(place, [AllergyTag.DAIRY])

        self.assertEqual(summary.verdict, Verdict.HIGH_RISK)
        self.assertTrue(all(item.impact.value == "negative" for item in evidence))

    def test_mixed_reviews_land_in_caution(self) -> None:
        place = {
            "rating": 4.1,
            "reviews": [
                {
                    "review_id": "1",
                    "rating": 5,
                    "text": "Great with gluten free requests and the menu was clearly labeled.",
                    "publish_time": "2026-02-01T12:00:00Z",
                },
                {
                    "review_id": "2",
                    "rating": 2,
                    "text": "They told me there was cross contamination in the same fryer, so be careful with celiac.",
                    "publish_time": "2025-11-01T12:00:00Z",
                },
            ],
        }

        summary, evidence, _ = analyze_place(place, [AllergyTag.WHEAT_GLUTEN])

        self.assertEqual(summary.verdict, Verdict.USE_CAUTION)
        self.assertGreaterEqual(len(evidence), 2)
        impacts = {item.impact.value for item in evidence}
        self.assertEqual(impacts, {"positive", "negative"})

    def test_no_allergy_reviews_stays_low_confidence(self) -> None:
        place = {
            "rating": 4.7,
            "reviews": [
                {
                    "review_id": "1",
                    "rating": 5,
                    "text": "Amazing pasta and service.",
                    "publish_time": "2026-03-01T12:00:00Z",
                }
            ],
        }

        summary, evidence, explanation = analyze_place(place, [AllergyTag.EGG])

        self.assertEqual(summary.evidence_count, 0)
        self.assertLess(summary.confidence, 0.25)
        self.assertEqual(summary.verdict, Verdict.USE_CAUTION)
        self.assertFalse(evidence)
        self.assertIn("little review evidence", explanation)

    def test_severe_negative_evidence_drops_score(self) -> None:
        place = {
            "rating": 3.9,
            "reviews": [
                {
                    "review_id": "1",
                    "rating": 1,
                    "text": "I have a shellfish allergy and had a reaction here after the server said it was safe.",
                    "publish_time": "2026-03-15T12:00:00Z",
                }
            ],
        }

        summary, _, _ = analyze_place(place, [AllergyTag.SHELLFISH])

        self.assertLessEqual(summary.score, 30)
        self.assertEqual(summary.verdict, Verdict.HIGH_RISK)


if __name__ == "__main__":
    unittest.main()

