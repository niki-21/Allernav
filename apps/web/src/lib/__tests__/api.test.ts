import assert from "node:assert/strict";
import test from "node:test";

import {
  buildMenuRefreshPayload,
  buildNearbySuggestionPayload,
  buildPlaceDetailsUrl,
  buildSearchPayload,
  shouldUseVisibleCandidates,
} from "../api.ts";

test("buildSearchPayload keeps query, center, and allergens aligned", () => {
  assert.deepEqual(
    buildSearchPayload("ramen", { lat: 1, lng: 2 }, ["peanut", "soy"]),
    {
      query: "ramen",
      center: { lat: 1, lng: 2 },
      allergens: ["peanut", "soy"],
    },
  );
});

test("buildPlaceDetailsUrl appends repeated allergen params", () => {
  assert.equal(
    buildPlaceDetailsUrl("abc 123", ["peanut", "soy"]),
    "/api/places/abc%20123?allergens=peanut&allergens=soy",
  );
});

test("buildMenuRefreshPayload includes restaurant name and website url", () => {
  assert.deepEqual(
    buildMenuRefreshPayload({
      placeName: "Nami Nori Williamsburg",
      websiteUrl: "https://example.com/menu",
    }),
    {
      restaurant_name: "Nami Nori Williamsburg",
      website_url: "https://example.com/menu",
    },
  );
});

test("buildNearbySuggestionPayload includes current map candidates", () => {
  assert.deepEqual(
    buildNearbySuggestionPayload(
      "suggest dinner",
      { lat: 40, lng: -73 },
      ["sesame"],
      ["place-a", "place-b"],
    ),
    {
      question: "suggest dinner",
      query: "suggest dinner",
      center: { lat: 40, lng: -73 },
      allergens: ["sesame"],
      candidate_place_ids: ["place-a", "place-b"],
      max_places: 2,
      top_evidence: 3,
    },
  );
});

test("buildNearbySuggestionPayload starts fresh search for cuisine prompts", () => {
  assert.deepEqual(
    buildNearbySuggestionPayload(
      "I want a french restaurant",
      { lat: 40, lng: -73 },
      ["sesame"],
      ["place-a", "place-b"],
    ),
    {
      question: "I want a french restaurant",
      query: "I want a french restaurant",
      center: { lat: 40, lng: -73 },
      allergens: ["sesame"],
      candidate_place_ids: [],
      max_places: 6,
      top_evidence: 3,
    },
  );
  assert.equal(shouldUseVisibleCandidates("Which visible place looks better?"), true);
  assert.equal(shouldUseVisibleCandidates("Find sushi nearby"), false);
});
