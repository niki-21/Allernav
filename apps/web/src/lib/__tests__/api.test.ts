import assert from "node:assert/strict";
import test from "node:test";

import { buildMenuRefreshPayload, buildPlaceDetailsUrl, buildSearchPayload } from "../api.ts";

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
