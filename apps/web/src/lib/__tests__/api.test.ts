import assert from "node:assert/strict";
import test from "node:test";

import { buildPlaceDetailsUrl, buildSearchPayload, getApiBaseUrl } from "../api.ts";

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
    buildPlaceDetailsUrl("http://localhost:8000", "abc 123", ["peanut", "soy"]),
    "http://localhost:8000/api/places/abc%20123?allergens=peanut&allergens=soy",
  );
});

test("getApiBaseUrl trims trailing slash", () => {
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://localhost:8000/";
  assert.equal(getApiBaseUrl(), "http://localhost:8000");
});
