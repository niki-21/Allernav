import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
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
    { id: "place-c", name: "Charlie", location: { lat: 40.2, lng: -73.2 } },
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
      candidate_place_ids: ["place-a", "place-b", "place-c"],
      candidate_places: candidates,
      allow_background_scan: false,
      max_places: 3,
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
      allow_background_scan: false,
      max_places: 2,
      top_evidence: 3,
    },
  );
});

test("nearby payload opts into controlled background scans", () => {
  const candidates = [{ id: "place-a", name: "Alpha", location: { lat: 40, lng: -73 } }];
  const payload = buildNearbySuggestionPayload(
    "compare nearby places",
    { lat: 40, lng: -73 },
    ["sesame"],
    candidates,
    true,
  );
  assert.equal(payload.allow_background_scan, true);
});

test("TrustPanel does not duplicate agent dish evidence in the menu tab", () => {
  const source = readFileSync(new URL("../../components/TrustPanel.tsx", import.meta.url), "utf8");
  assert.equal(source.includes("Agent dish evidence"), false);
  assert.equal(source.includes("Dish evidence found by agent analysis"), false);
});

test("menu rows hide repeated confidence and RAG cards show one restaurant score", () => {
  const trustPanelSource = readFileSync(new URL("../../components/TrustPanel.tsx", import.meta.url), "utf8");
  const pageSource = readFileSync(new URL("../../app/page.tsx", import.meta.url), "utf8");
  assert.equal(trustPanelSource.includes("confidenceText"), false);
  assert.equal((pageSource.match(/suggestion\.restaurant_fit_score/g) ?? []).length, 1);
  assert.equal(pageSource.includes("nearbyBucketSummary(suggestion)"), true);
});

test("Menu tab leads with the fit score and possible lower-risk section", () => {
  const source = readFileSync(new URL("../../components/TrustPanel.tsx", import.meta.url), "utf8");
  const possibleIndex = source.indexOf('title: "Possible lower-risk items to ask about"');
  const checkIndex = source.indexOf('title: "Needs staff check"');
  const avoidIndex = source.indexOf('title: "Avoid for your allergies"');
  const insufficientIndex = source.indexOf('title: "Insufficient info"');

  assert.ok(source.includes("Restaurant allergy fit:"));
  assert.ok(possibleIndex < checkIndex && checkIndex < avoidIndex && avoidIndex < insufficientIndex);
  assert.ok(source.includes('<details className="menu-trace">'));
  assert.equal(source.includes('<details className="menu-trace" open>'), false);
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
