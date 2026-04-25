import assert from "node:assert/strict";
import test from "node:test";

import { applyPlaceDetailError, applyPlaceDetailSuccess, seedPlaceDetailsState } from "../placeState.ts";

test("seedPlaceDetailsState starts each place in loading", () => {
  assert.deepEqual(seedPlaceDetailsState(["a", "b"]), {
    a: { status: "loading" },
    b: { status: "loading" },
  });
});

test("applyPlaceDetailSuccess stores scored details without removing others", () => {
  const next = applyPlaceDetailSuccess(
    seedPlaceDetailsState(["a", "b"]),
    "a",
    {
      id: "a",
      name: "Alpha",
      address: "123 Main",
      location: { lat: 1, lng: 2 },
      google_maps_uri: "https://example.com/map",
      google_review_uri: "https://example.com/review",
      selected_allergens: ["peanut"],
      score_summary: {
        score: 88,
        verdict: "good_fit",
        confidence: 0.7,
        fit_score: 88,
        fit_verdict: "good_fit",
        evidence_confidence: 0.7,
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
  );

  assert.equal(next.a.status, "ready");
  assert.equal(next.b.status, "loading");
});

test("applyPlaceDetailError preserves failure message", () => {
  const next = applyPlaceDetailError({}, "a", "boom");
  assert.deepEqual(next, {
    a: { status: "error", message: "boom" },
  });
});
