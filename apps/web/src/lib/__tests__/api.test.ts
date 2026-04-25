import assert from "node:assert/strict";
import test from "node:test";

import { buildPlaceDetailsUrl, buildSearchPayload } from "../api.ts";

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
