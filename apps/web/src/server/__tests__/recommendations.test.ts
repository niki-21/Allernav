import assert from "node:assert/strict";
import test from "node:test";

import { recommendMenuItems } from "../recommendations.ts";

test("recommendMenuItems avoids menu items that mention selected allergens", async () => {
  const recommendations = await recommendMenuItems(
    "Test Cafe",
    ["shellfish", "peanut"],
    {
      source_url: "https://example.com/menu",
      sections: [
        {
          title: "Entrees",
          items: [
            {
              name: "Grilled Chicken Bowl",
              description: "Rice, greens, lemon herb sauce",
              price: "$15",
              likely_safe_for: [],
              likely_risky_for: [],
            },
            {
              name: "Shrimp Satay",
              description: "Peanut glaze",
              price: "$18",
              likely_safe_for: [],
              likely_risky_for: [],
            },
          ],
        },
      ],
    },
    [],
  );

  assert.equal(recommendations[0]?.name, "Grilled Chicken Bowl");
  assert.ok(!recommendations.some((item) => item.name === "Shrimp Satay"));
});

test("recommendMenuItems upgrades caution when reviews mention cross-contact", async () => {
  const recommendations = await recommendMenuItems(
    "Test Cafe",
    ["wheat_gluten"],
    {
      source_url: "https://example.com/menu",
      sections: [
        {
          title: "Entrees",
          items: [
            {
              name: "Grilled Chicken Bowl",
              description: "Rice, greens, lemon herb sauce",
              price: "$15",
              likely_safe_for: [],
              likely_risky_for: [],
            },
          ],
        },
      ],
    },
    [
      {
        review_id: "1",
        text: "Shared fryer was a problem for celiac.",
        matched_allergens: ["wheat_gluten"],
        signal_type: "cross_contact_risk",
        impact: "negative",
        excerpt: "Shared fryer was a problem for celiac.",
        matched_phrase: "shared fryer",
        signal_label: "Cross-contact risk mentioned",
        tone: "risk_note",
        is_allergy_relevant: true,
        weight: 1.6,
      },
    ],
  );

  assert.match(recommendations[0]?.caution ?? "", /shared fryers|cross-contact/i);
});

test("recommendMenuItems respects structured risky allergen tags", async () => {
  const recommendations = await recommendMenuItems(
    "Honey Pig",
    ["soy", "sesame"],
    {
      source_url: null,
      sections: [
        {
          title: "Korean BBQ",
          items: [
            {
              name: "Beef Bulgogi",
              description: "Thinly sliced marinated beef.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["soy", "sesame"],
            },
            {
              name: "Pork Belly",
              description: "Unmarinated pork belly for shared-grill barbecue.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: [],
            },
          ],
        },
      ],
    },
    [],
  );

  assert.equal(recommendations.length, 0);
});

test("recommendMenuItems avoids promoting shared-prep items", async () => {
  const recommendations = await recommendMenuItems(
    "Test BBQ",
    ["dairy"],
    {
      source_url: null,
      sections: [
        {
          title: "Entrees",
          items: [
            {
              name: "Shared Grill Chicken",
              description: "Chicken cooked on a shared grill.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: [],
            },
            {
              name: "Cold Brew",
              description: "Black cold brew coffee.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: [],
            },
          ],
        },
      ],
    },
    [],
  );

  assert.deepEqual(
    recommendations.map((item) => item.name),
    ["Cold Brew"],
  );
});
