import assert from "node:assert/strict";
import test from "node:test";

import { rankPlaces, shouldShowSearchAreaButton } from "../placeRanking.ts";

test("shouldShowSearchAreaButton turns on after a meaningful map move", () => {
  assert.equal(
    shouldShowSearchAreaButton({ lat: 40.741895, lng: -73.989308 }, { lat: 40.7419, lng: -73.9893 }),
    false,
  );
  assert.equal(
    shouldShowSearchAreaButton({ lat: 40.741895, lng: -73.989308 }, { lat: 40.748, lng: -73.98 }),
    true,
  );
});

test("rankPlaces prioritizes meaningful allergy evidence and fit score", () => {
  const ranked = rankPlaces(
    [
      { id: "a", name: "Alpha", location: { lat: 1, lng: 1 }, rating: 4.2 },
      { id: "b", name: "Bravo", location: { lat: 1, lng: 2 }, rating: 4.7 },
      { id: "c", name: "Charlie", location: { lat: 1, lng: 3 }, rating: 4.9 },
    ],
    {
      a: {
        status: "ready",
        data: {
          id: "a",
          name: "Alpha",
          location: { lat: 1, lng: 1 },
          google_maps_uri: "https://example.com/a",
          google_review_uri: "https://example.com/a/review",
          selected_allergens: ["peanut"],
          score_summary: {
            score: 50,
            verdict: "use_caution",
            confidence: 0.22,
            fit_score: 50,
            fit_verdict: "use_caution",
            evidence_confidence: 0.22,
            positive_signals: [],
            negative_signals: [],
            evidence_count: 0,
            meaningful_evidence: false,
            evidence_status: "limited",
            evidence_summary: "Not enough allergy-specific review evidence",
          },
          evidence: [],
          explanation: "Limited evidence",
          menu: null,
          recommended_items: [],
          community_reviews: [],
        },
      },
      b: {
        status: "ready",
        data: {
          id: "b",
          name: "Bravo",
          location: { lat: 1, lng: 2 },
          google_maps_uri: "https://example.com/b",
          google_review_uri: "https://example.com/b/review",
          selected_allergens: ["peanut"],
          score_summary: {
            score: 80,
            verdict: "good_fit",
            confidence: 0.6,
            fit_score: 80,
            fit_verdict: "good_fit",
            evidence_confidence: 0.6,
            positive_signals: ["Knowledgeable staff"],
            negative_signals: [],
            evidence_count: 2,
            meaningful_evidence: true,
            evidence_status: "meaningful",
            evidence_summary: "2 allergy-aware review signals",
          },
          evidence: [],
          explanation: "Positive evidence",
          menu: null,
          recommended_items: [],
          community_reviews: [],
        },
      },
    },
  );

  assert.deepEqual(
    ranked.map((place) => place.id),
    ["b", "a", "c"],
  );
});
