import assert from "node:assert/strict";
import test from "node:test";

import { getPlaceDetailsService, searchPlacesService } from "../service.ts";
import { normalizeApifyReviews } from "../apifyReviews.ts";
import { normalizeBackendMenu } from "../fastapi.ts";

const fakeClient = {
  async searchPlaces(_query: string, center: { lat: number; lng: number }) {
    return [
      {
        id: "alpha",
        name: "Alpha Cafe",
        address: "123 Main St",
        location: center,
        rating: 4.5,
        user_rating_count: 42,
        primary_type: "restaurant",
      },
    ];
  },
  async getPlaceDetails(placeId: string) {
    return {
      id: placeId,
      name: "Alpha Cafe",
      address: "123 Main St",
      location: { lat: 38.9, lng: -77.0 },
      rating: 4.5,
      user_rating_count: 42,
      primary_type: "restaurant",
      website_uri: "https://example.com",
      editorial_summary: "Modern cafe",
      reviews: [
        {
          review_id: "1",
          rating: 5,
          text: "The staff understood my peanut allergy and double checked the fryer.",
          publish_time: "2026-02-20T12:00:00Z",
        },
      ],
    };
  },
};

test("searchPlacesService returns the expected response shape", async () => {
  const response = await searchPlacesService(
    {
      query: "ramen",
      center: { lat: 38.9, lng: -77.0 },
      allergens: ["peanut"],
    },
    fakeClient,
  );

  assert.equal(response.query, "ramen");
  assert.equal(response.center.lat, 38.9);
  assert.equal(response.places[0]?.id, "alpha");
  assert.deepEqual(response.allergens, ["peanut"]);
});

test("getPlaceDetailsService returns details, evidence, and explanation", async () => {
  const response = await getPlaceDetailsService("alpha", ["peanut"], fakeClient);

  assert.equal(response.id, "alpha");
  assert.deepEqual(response.selected_allergens, ["peanut"]);
  assert.ok(response.score_summary);
  assert.ok(response.evidence.length >= 1);
  assert.ok(response.explanation.length > 0);
  assert.ok(response.decision_brief.headline.length > 0);
  assert.ok(response.decision_brief.caution_flags.length > 0);
  assert.match(response.google_review_uri, /writereview/);
});

test("getPlaceDetailsService stays cautious when reviews are missing", async () => {
  const noReviewClient = {
    ...fakeClient,
    async getPlaceDetails(placeId: string) {
      const place = await fakeClient.getPlaceDetails(placeId);
      return { ...place, reviews: [] };
    },
  };

  const response = await getPlaceDetailsService("alpha", ["peanut"], noReviewClient);

  assert.equal(response.score_summary.evidence_count, 0);
  assert.equal(response.score_summary.verdict, "use_caution");
});

test("getPlaceDetailsService prioritizes allergy-relevant Google review snippets", async () => {
  const mixedReviewClient = {
    ...fakeClient,
    async getPlaceDetails(placeId: string) {
      const place = await fakeClient.getPlaceDetails(placeId);
      return {
        ...place,
        reviews: [
          {
            review_id: "generic-1",
            rating: 5,
            text: "Great patio and fast service.",
            publish_time: "2026-01-10T12:00:00Z",
          },
          {
            review_id: "generic-2",
            rating: 4,
            text: "The noodles were excellent.",
            publish_time: "2026-01-11T12:00:00Z",
          },
          {
            review_id: "allergy-1",
            rating: 2,
            text: "They warned me about cross-contact for my sesame allergy.",
            publish_time: "2026-01-12T12:00:00Z",
          },
        ],
      };
    },
  };

  const response = await getPlaceDetailsService("alpha", ["sesame"], mixedReviewClient);

  assert.equal(response.review_snippets[0]?.review_id, "allergy-1");
  assert.equal(response.evidence[0]?.review_id, "allergy-1");
});

test("normalizeApifyReviews maps Apify review data", () => {
  const reviews = normalizeApifyReviews([
    {
      reviews: [
        {
          reviewId: "apify-1",
          authorName: "Pat",
          text: "The staff warned me about sesame cross-contact.",
          rating: "2",
          timestamp: 1780000000,
        },
      ],
    },
  ]);

  assert.equal(reviews.length, 1);
  assert.equal(reviews[0]?.review_id, "apify-1");
  assert.equal(reviews[0]?.author_name, "Pat");
  assert.equal(reviews[0]?.rating, 2);
  assert.match(reviews[0]?.text ?? "", /sesame/);
});

test("normalizeBackendMenu preserves OCR extraction metadata", () => {
  const menu = normalizeBackendMenu({
    source_url: "https://example.com/menu.pdf",
    source_fetched_at: "2026-06-26T00:00:00Z",
    status: "complete",
    content_type: "application/pdf",
    document_url: "https://example.com/menu.pdf",
    document_urls: ["https://example.com/page-1.jpg", "https://example.com/page-2.jpg"],
    menu_version: "May 2026",
    extraction_method: "azure_document_intelligence_read",
    page_count: 2,
    extraction_confidence: 0.91,
    restaurant_fit_score: 47,
    restaurant_fit_label: "Higher concern",
    avoid_count: 1,
    needs_check_count: 8,
    possible_lower_risk_count: 3,
    sections: [
      {
        title: "Crepes",
        items: [
          {
            name: "Normandie Crepe",
            description: "Apples and cream",
            risk_label: "avoid",
            matched_allergens: ["dairy"],
            risk_reasons: ["Menu text identifies dairy."],
            verification_question: "Can you confirm the dairy ingredients?",
            confidence: 0.88,
            source_page: 1,
            source_url: "https://example.com/page-1.jpg",
            ocr_confidence: 0.91,
          },
        ],
      },
    ],
  });

  assert.equal(menu?.source_url, "https://example.com/menu.pdf");
  assert.equal(menu?.extraction_method, "azure_document_intelligence_read");
  assert.equal(menu?.page_count, 2);
  assert.equal(menu?.extraction_confidence, 0.91);
  assert.equal(menu?.restaurant_fit_score, 47);
  assert.equal(menu?.restaurant_fit_label, "Higher concern");
  assert.equal(menu?.avoid_count, 1);
  assert.equal(menu?.needs_check_count, 8);
  assert.equal(menu?.possible_lower_risk_count, 3);
  assert.equal(menu?.menu_version, "May 2026");
  assert.equal(menu?.document_urls?.length, 2);
  assert.equal(menu?.sections[0]?.items[0]?.source_page, 1);
  assert.equal(menu?.sections[0]?.items[0]?.risk_label, "avoid");
  assert.deepEqual(menu?.sections[0]?.items[0]?.matched_allergens, ["dairy"]);
  assert.equal(menu?.sections[0]?.items[0]?.confidence, 0.88);
});

test("getPlaceDetailsService defers Apify reviews even when configured", async () => {
  const previousToken = process.env.APIFY_TOKEN;
  const previousLimit = process.env.APIFY_REVIEWS_LIMIT;
  const previousFetch = globalThis.fetch;
  process.env.APIFY_TOKEN = "test-token";
  process.env.APIFY_REVIEWS_LIMIT = "25";
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    assert.ok(!url.includes("api.apify.com"), "place details should not call Apify directly");
    assert.equal(init?.method, undefined);
    return new Response(JSON.stringify({ sections: [] }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  try {
    const response = await getPlaceDetailsService("apify-alpha", ["sesame"], fakeClient);

    assert.notEqual(response.review_snippets[0]?.review_id, "apify-review");
    assert.equal(response.review_source_summary?.expanded_review_count, 0);
    assert.equal(response.review_source_summary?.expanded_review_status, "deferred");
  } finally {
    if (previousToken === undefined) {
      delete process.env.APIFY_TOKEN;
    } else {
      process.env.APIFY_TOKEN = previousToken;
    }
    if (previousLimit === undefined) {
      delete process.env.APIFY_REVIEWS_LIMIT;
    } else {
      process.env.APIFY_REVIEWS_LIMIT = previousLimit;
    }
    globalThis.fetch = previousFetch;
  }
});

test("getPlaceDetailsService uses local snapshot menus for demo restaurants", async () => {
  const localSnapshotClient = {
    ...fakeClient,
    async getPlaceDetails(placeId: string) {
      return {
        id: placeId,
        name: "The Board and Brew",
        address: "8150 Baltimore Ave",
        location: { lat: 38.98, lng: -76.94 },
        rating: 4.2,
        user_rating_count: 88,
        primary_type: "cafe",
        website_uri: null,
        editorial_summary: "Cafe near campus",
        reviews: [],
      };
    },
  };

  const response = await getPlaceDetailsService("board-and-brew", ["dairy"], localSnapshotClient);

  assert.equal(response.menu?.sections[0]?.title, "Cafe Favorites");
  assert.ok((response.recommended_items.length ?? 0) > 0);
});

test("getPlaceDetailsService changes score by selected allergens when menu risk changes", async () => {
  const honeyPigClient = {
    ...fakeClient,
    async getPlaceDetails(placeId: string) {
      return {
        id: placeId,
        name: "Honey Pig BBQ",
        address: "7326 Baltimore Ave",
        location: { lat: 38.99, lng: -76.93 },
        rating: 4.4,
        user_rating_count: 320,
        primary_type: "restaurant",
        website_uri: null,
        editorial_summary: "Korean BBQ spot",
        reviews: [],
      };
    },
  };

  const dairyResponse = await getPlaceDetailsService("honey-pig", ["dairy"], honeyPigClient);
  const soySesameResponse = await getPlaceDetailsService("honey-pig", ["soy", "sesame"], honeyPigClient);

  assert.ok(dairyResponse.score_summary.fit_score > soySesameResponse.score_summary.fit_score);
  assert.equal(soySesameResponse.score_summary.fit_verdict, "high_risk");
});
