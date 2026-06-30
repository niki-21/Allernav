import assert from "node:assert/strict";
import test from "node:test";

import {
  buildMenuRefreshPayload,
  buildNearbySuggestionPayload,
  buildPlaceDetailsUrl,
  buildSearchPayload,
  menuScanErrorMessage,
  nearbyRagErrorMessage,
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
  const candidates = [
    { id: "place-a", name: "Alpha", location: { lat: 40, lng: -73 } },
    { id: "place-b", name: "Bravo", location: { lat: 40.1, lng: -73.1 } },
  ];
  assert.deepEqual(
    buildNearbySuggestionPayload(
      "suggest dinner",
      { lat: 40, lng: -73 },
      ["sesame"],
      candidates,
    ),
    {
      question: "suggest dinner",
      query: "suggest dinner",
      center: { lat: 40, lng: -73 },
      allergens: ["sesame"],
      candidate_place_ids: ["place-a", "place-b"],
      candidate_places: candidates,
      max_places: 2,
      top_evidence: 3,
    },
  );
});

test("buildNearbySuggestionPayload keeps visible candidates for cuisine prompts", () => {
  const candidates = [
    { id: "place-a", name: "Alpha", location: { lat: 40, lng: -73 } },
    { id: "place-b", name: "Bravo", location: { lat: 40.1, lng: -73.1 } },
  ];
  assert.deepEqual(
    buildNearbySuggestionPayload(
      "I want a french restaurant",
      { lat: 40, lng: -73 },
      ["sesame"],
      candidates,
    ),
    {
      question: "I want a french restaurant",
      query: "I want a french restaurant",
      center: { lat: 40, lng: -73 },
      allergens: ["sesame"],
      candidate_place_ids: ["place-a", "place-b"],
      candidate_places: candidates,
      max_places: 2,
      top_evidence: 3,
    },
  );
});

test("menuScanErrorMessage converts abort and timeout errors to user-facing copy", () => {
  assert.equal(
    menuScanErrorMessage(new DOMException("The operation was aborted due to timeout", "TimeoutError")),
    "The scan took too long. Try again or open the restaurant panel.",
  );
  assert.equal(
    menuScanErrorMessage('{"detail":"The signal timed out"}'),
    "The scan took too long. Try again or open the restaurant panel.",
  );
});

test("menuScanErrorMessage hides malformed JSON responses", () => {
  assert.equal(
    menuScanErrorMessage("{invalid-json"),
    "The scan took too long. Try again or open the restaurant panel.",
  );
});

test("nearbyRagErrorMessage converts aborts and raw responses to product copy", () => {
  assert.equal(
    nearbyRagErrorMessage(new DOMException("This operation was aborted", "AbortError")),
    "This request took too long. Try a specific restaurant or scan the menu first.",
  );
  assert.equal(
    nearbyRagErrorMessage('{"detail":"upstream failed"}'),
    "Nearby suggestions are temporarily unavailable. Try again shortly.",
  );
});
