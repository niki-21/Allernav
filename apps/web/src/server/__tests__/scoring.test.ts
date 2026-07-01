import assert from "node:assert/strict";
import test from "node:test";

import { analyzePlace } from "../scoring.ts";

test("no-allergy analysis uses general restaurant signals", () => {
  const { summary, evidence, explanation } = analyzePlace(
    { rating: 4.7, reviews: [] },
    [],
  );
  assert.equal(summary.evidence_status, "general");
  assert.equal(summary.fit_score, 94);
  assert.equal(evidence.length, 0);
  assert.match(explanation, /No allergies selected/);
});

test("direct allergen accommodation scores well", () => {
  const { summary, evidence } = analyzePlace(
    {
      rating: 4.6,
      reviews: [
        {
          review_id: "1",
          rating: 5,
          text: "I have a peanut allergy and felt safe here. The staff understood and double checked everything.",
          publish_time: "2026-01-10T12:00:00Z",
        },
      ],
    },
    ["peanut"],
  );

  assert.ok(summary.score >= 70);
  assert.equal(summary.verdict, "good_fit");
  assert.ok(summary.evidence_count >= 2);
  assert.ok(evidence.some((item) => item.matched_allergens.length > 0));
});

test("false positive phrase stays negative", () => {
  const { summary, evidence } = analyzePlace(
    {
      rating: 2.8,
      reviews: [
        {
          review_id: "1",
          rating: 2,
          text: "Definitely not allergy friendly. The staff didn't understand my dairy allergy at all.",
          publish_time: "2025-12-10T12:00:00Z",
        },
      ],
    },
    ["dairy"],
  );

  assert.equal(summary.verdict, "high_risk");
  assert.ok(evidence.every((item) => item.impact === "negative"));
});

test("mixed reviews land in caution", () => {
  const { summary, evidence } = analyzePlace(
    {
      rating: 4.1,
      reviews: [
        {
          review_id: "1",
          rating: 5,
          text: "Great with gluten free requests and the menu was clearly labeled.",
          publish_time: "2026-02-01T12:00:00Z",
        },
        {
          review_id: "2",
          rating: 2,
          text: "They told me there was cross contamination in the same fryer, so be careful with celiac.",
          publish_time: "2025-11-01T12:00:00Z",
        },
      ],
    },
    ["wheat_gluten"],
  );

  assert.equal(summary.verdict, "use_caution");
  assert.ok(evidence.length >= 2);
  assert.deepEqual(new Set(evidence.map((item) => item.impact)), new Set(["positive", "negative"]));
});

test("no allergy reviews stays low confidence", () => {
  const { summary, evidence, explanation } = analyzePlace(
    {
      rating: 4.7,
      reviews: [
        {
          review_id: "1",
          rating: 5,
          text: "Amazing pasta and service.",
          publish_time: "2026-03-01T12:00:00Z",
        },
      ],
    },
    ["egg"],
  );

  assert.equal(summary.evidence_count, 0);
  assert.ok(summary.confidence < 0.25);
  assert.equal(summary.verdict, "use_caution");
  assert.equal(evidence.length, 0);
  assert.match(explanation, /little review evidence/i);
});

test("severe negative evidence drops score", () => {
  const { summary } = analyzePlace(
    {
      rating: 3.9,
      reviews: [
        {
          review_id: "1",
          rating: 1,
          text: "I have a shellfish allergy and had a reaction here after the server said it was safe.",
          publish_time: "2026-03-15T12:00:00Z",
        },
      ],
    },
    ["shellfish"],
  );

  assert.ok(summary.score <= 30);
  assert.equal(summary.verdict, "high_risk");
});

test("generic bad-service complaints do not become allergy risk evidence", () => {
  const { summary, evidence } = analyzePlace(
    {
      rating: 1.2,
      reviews: [
        {
          review_id: "1",
          rating: 1,
          text: "This place felt unsafe, dirty, and unprofessional. I would never come back.",
          publish_time: "2026-03-15T12:00:00Z",
        },
      ],
    },
    ["tree_nut"],
  );

  assert.equal(summary.evidence_count, 0);
  assert.equal(summary.meaningful_evidence, false);
  assert.equal(evidence.length, 0);
});

test("allergen terms require word boundaries", () => {
  const { summary, evidence } = analyzePlace(
    {
      rating: 1.5,
      reviews: [
        {
          review_id: "1",
          rating: 1,
          text: "The music is very loud and the service was offish, but this review says nothing about food allergies.",
          publish_time: "2026-03-15T12:00:00Z",
        },
      ],
    },
    ["fish"],
  );

  assert.equal(summary.evidence_count, 0);
  assert.equal(evidence.length, 0);
});
