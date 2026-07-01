import { ALLERGEN_OPTIONS } from "../lib/allergens.ts";
import type { AllergyTag, LatLng, PlaceDetailsResponse, PlaceMenu, PlaceScoreSummary, PlaceSummary, SearchResponse } from "../lib/types.ts";
import { buildDecisionBrief } from "./briefing.ts";
import { fetchBackendPlaceMenu } from "./fastapi.ts";
import { GooglePlacesClient, type GooglePlaceDetails, type GooglePlaceReview } from "./googlePlaces.ts";
import { getLocalPlaceSnapshot } from "./localPlaceSnapshots.ts";
import { recommendMenuItems } from "./recommendations.ts";
import { analyzePlace } from "./scoring.ts";

export const DEFAULT_CENTER: LatLng = { lat: 40.741895, lng: -73.989308 };

const ALLERGY_TAGS = new Set<AllergyTag>(ALLERGEN_OPTIONS.map((option) => option.value));

const REVIEW_GENERIC_ALLERGY_TERMS = [
  "allergy",
  "allergic",
  "allergen",
  "cross contact",
  "cross-contact",
  "cross contamination",
  "cross-contamination",
  "dedicated fryer",
  "separate fryer",
  "gluten free",
  "gluten-free",
  "celiac",
];

const REVIEW_ALLERGEN_TERMS: Record<AllergyTag, string[]> = {
  peanut: ["peanut", "peanuts", "peanut oil"],
  tree_nut: ["tree nut", "tree nuts", "almond", "walnut", "cashew", "pecan", "pistachio", "hazelnut"],
  dairy: ["dairy", "milk", "butter", "cheese", "cream", "lactose"],
  egg: ["egg", "eggs", "mayo", "aioli"],
  shellfish: ["shellfish", "shrimp", "prawn", "lobster", "crab", "scallop"],
  fish: ["fish", "salmon", "tuna", "anchovy", "cod"],
  soy: ["soy", "soybean", "soy sauce", "tofu", "edamame"],
  sesame: ["sesame", "tahini"],
  wheat_gluten: ["gluten", "wheat", "celiac", "flour", "bread", "pasta", "soy sauce"],
};

export interface SearchRequestPayload {
  query?: string;
  center?: LatLng | null;
  allergens?: AllergyTag[];
  max_results?: number;
  maxResults?: number;
}

export interface PlacesClientLike {
  searchPlaces(query: string, center: LatLng, maxResults?: number): Promise<PlaceSummary[]>;
  getPlaceDetails(placeId: string): Promise<GooglePlaceDetails>;
}

function clampMaxResults(value: number | undefined): number {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return 12;
  }
  return Math.max(1, Math.min(20, Math.trunc(value)));
}

export function isAllergyTag(value: string): value is AllergyTag {
  return ALLERGY_TAGS.has(value as AllergyTag);
}

function hasSharedPrepRisk(name: string, description?: string | null): boolean {
  const haystack = `${name} ${description ?? ""}`.toLowerCase();
  return /fried|crispy|tempura|shared|sampler|combo|tabletop|bbq|barbecue|fryer/.test(haystack);
}

function clampScore(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function roundConfidence(value: number): number {
  return Math.round(value * 100) / 100;
}

function reviewRelevanceScore(
  review: GooglePlaceReview,
  selectedAllergens: AllergyTag[],
  evidenceReviewIds: Set<string>,
): number {
  const text = review.text.toLowerCase();
  let score = evidenceReviewIds.has(review.review_id) ? 100 : 0;

  for (const allergen of selectedAllergens) {
    if (REVIEW_ALLERGEN_TERMS[allergen].some((term) => termMatches(text, term))) {
      score += 25;
    }
  }
  if (REVIEW_GENERIC_ALLERGY_TERMS.some((term) => termMatches(text, term))) {
    score += 12;
  }
  if (typeof review.rating === "number" && review.rating <= 2) {
    score += 3;
  }
  if (review.publish_time) {
    const publishedAt = Date.parse(review.publish_time);
    if (!Number.isNaN(publishedAt)) {
      const ageDays = Math.floor((Date.now() - publishedAt) / (1000 * 60 * 60 * 24));
      if (ageDays <= 365) {
        score += 2;
      }
    }
  }

  return score;
}

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function termMatches(text: string, term: string): boolean {
  const normalizedTerm = term.toLowerCase().trim();
  if (!normalizedTerm) {
    return false;
  }
  const pattern = normalizedTerm.includes(" ")
    ? escapeRegex(normalizedTerm).replace(/\s+/g, "\\s+")
    : escapeRegex(normalizedTerm);
  return new RegExp(`(^|[^a-z0-9])${pattern}([^a-z0-9]|$)`, "i").test(text);
}

function prioritizeReviewSnippets(
  reviews: GooglePlaceReview[],
  selectedAllergens: AllergyTag[],
  evidenceReviewIds: Set<string>,
): GooglePlaceReview[] {
  return reviews
    .filter((review) => review.text.trim().length > 0)
    .map((review, index) => ({
      review,
      index,
      score: reviewRelevanceScore(review, selectedAllergens, evidenceReviewIds),
    }))
    .sort((left, right) => right.score - left.score || left.index - right.index)
    .slice(0, 5)
    .map(({ review }) => review);
}

function mergeReviewSources(
  googleReviews: GooglePlaceReview[],
  externalReviews: GooglePlaceReview[],
): GooglePlaceReview[] {
  const merged: GooglePlaceReview[] = [];
  const seen = new Set<string>();

  for (const review of [...externalReviews, ...googleReviews]) {
    const text = review.text.trim();
    if (!text) {
      continue;
    }
    const key = review.review_id || text;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    merged.push(review);
  }

  return merged;
}

function buildMenuEvidenceSummary(
  riskyCount: number,
  recommendedCount: number,
  sharedPrepCount: number,
): string {
  if (riskyCount >= Math.max(3, recommendedCount + 2) || sharedPrepCount >= 2) {
    return "Menu evidence leans risky for selected allergens";
  }
  if (recommendedCount >= 2) {
    return "Menu evidence shows a few lower-risk items to verify";
  }
  if (recommendedCount === 1) {
    return "Menu evidence shows one simpler item to verify";
  }
  if (riskyCount > 0) {
    return "Menu evidence is mixed for selected allergens";
  }
  return "Menu evidence only";
}

function applyMenuSignals(
  summary: PlaceScoreSummary,
  menu: PlaceMenu | null,
  allergens: AllergyTag[],
  recommendedCount: number,
): PlaceScoreSummary {
  if (!menu || menu.sections.length === 0) {
    return summary;
  }

  const items = menu.sections.flatMap((section) => section.items);
  if (items.length === 0) {
    return summary;
  }

  const riskyCount = items.filter((item) => item.likely_risky_for.some((allergen) => allergens.includes(allergen))).length;
  const sharedPrepCount = items.filter((item) => hasSharedPrepRisk(item.name, item.description)).length;
  const adjustment = Math.max(-18, Math.min(12, recommendedCount * 5 - riskyCount * 4 - sharedPrepCount * 2));
  const adjustedScore = clampScore(summary.fit_score + adjustment);
  const menuConfidence = Math.min(0.44, 0.2 + items.length * 0.015 + recommendedCount * 0.05 + riskyCount * 0.015);
  const adjustedConfidence = summary.meaningful_evidence
    ? summary.evidence_confidence
    : Math.max(summary.evidence_confidence, menuConfidence);

  let adjustedVerdict = summary.fit_verdict;
  if (!summary.meaningful_evidence) {
    adjustedVerdict =
      adjustedScore <= 38 || riskyCount >= Math.max(3, recommendedCount + 2) ? "high_risk" : "use_caution";
  } else if (summary.fit_verdict === "high_risk" || adjustedScore <= 32) {
    adjustedVerdict = "high_risk";
  } else if (adjustedScore >= 72 && adjustedConfidence >= 0.42) {
    adjustedVerdict = "good_fit";
  } else {
    adjustedVerdict = "use_caution";
  }

  return {
    ...summary,
    score: adjustedScore,
    verdict: adjustedVerdict,
    confidence: roundConfidence(adjustedConfidence),
    fit_score: adjustedScore,
    fit_verdict: adjustedVerdict,
    evidence_confidence: roundConfidence(adjustedConfidence),
    evidence_summary: summary.meaningful_evidence
      ? summary.evidence_summary
      : buildMenuEvidenceSummary(riskyCount, recommendedCount, sharedPrepCount),
  };
}

export async function searchPlacesService(
  payload: SearchRequestPayload,
  client: PlacesClientLike = new GooglePlacesClient(),
): Promise<SearchResponse> {
  const center = payload.center ?? DEFAULT_CENTER;
  const allergens = payload.allergens ?? [];
  const maxResults = clampMaxResults(payload.max_results ?? payload.maxResults);
  const places = await client.searchPlaces(payload.query?.trim() ?? "", center, maxResults);

  return {
    query: payload.query?.trim() ?? "",
    center,
    allergens,
    places,
  };
}

export async function getPlaceDetailsService(
  placeId: string,
  allergens: AllergyTag[],
  client: PlacesClientLike = new GooglePlacesClient(),
): Promise<PlaceDetailsResponse> {
  const selectedAllergens: AllergyTag[] = allergens;
  const place = await client.getPlaceDetails(placeId);
  const localSnapshot = getLocalPlaceSnapshot(place.name);
  const googleReviewCount = place.reviews.length;
  const localReviewCount = localSnapshot?.reviews?.length ?? 0;
  const mergedPlace = {
    ...place,
    reviews: mergeReviewSources([...place.reviews, ...(localSnapshot?.reviews ?? [])], []),
  };
  const { summary, evidence, explanation } = analyzePlace(mergedPlace, selectedAllergens);
  const evidenceReviewIds = new Set(evidence.map((item) => item.review_id));
  const prioritizedReviews = prioritizeReviewSnippets(mergedPlace.reviews, selectedAllergens, evidenceReviewIds);
  const storedMenu = await fetchBackendPlaceMenu(place.id, selectedAllergens);
  const menu = storedMenu ?? localSnapshot?.menu ?? null;
  const recommendedItems = selectedAllergens.length > 0
    ? await recommendMenuItems(place.name, selectedAllergens, menu, evidence)
    : [];
  const scoreSummary = selectedAllergens.length > 0
    ? applyMenuSignals(summary, menu, selectedAllergens, recommendedItems.length)
    : summary;
  const decisionBrief = selectedAllergens.length > 0
    ? buildDecisionBrief(scoreSummary, evidence, menu, recommendedItems)
    : {
        headline: "Restaurant match",
        summary: "No allergies selected, so this view uses general restaurant signals.",
        recommended_action: "Review the menu, rating, and restaurant details.",
        caution_flags: [],
      };

  return {
    id: place.id,
    name: place.name,
    address: place.address ?? null,
    location: place.location,
    rating: place.rating ?? null,
    user_rating_count: place.user_rating_count ?? null,
    primary_type: place.primary_type ?? null,
    website_uri: place.website_uri ?? null,
    editorial_summary: place.editorial_summary ?? null,
    national_phone_number: place.national_phone_number ?? null,
    international_phone_number: place.international_phone_number ?? null,
    price_level: place.price_level ?? null,
    price_range: place.price_range ?? null,
    regular_opening_hours: place.regular_opening_hours ?? null,
    current_opening_hours: place.current_opening_hours ?? null,
    service_options: place.service_options ?? {},
    google_maps_uri:
      place.google_maps_uri ??
      `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(place.name)}&query_place_id=${encodeURIComponent(place.id)}`,
    google_review_uri: `https://search.google.com/local/writereview?placeid=${encodeURIComponent(place.id)}`,
    selected_allergens: selectedAllergens,
    score_summary: scoreSummary,
    restaurant_fit_score: selectedAllergens.length > 0 ? menu?.restaurant_fit_score ?? null : null,
    restaurant_fit_label: selectedAllergens.length > 0 ? menu?.restaurant_fit_label ?? null : null,
    evidence,
    review_snippets: prioritizedReviews
      .map((review) => ({
        review_id: review.review_id,
        author_name: review.author_name ?? null,
        rating: review.rating ?? null,
        text: review.text,
        publish_time: review.publish_time ?? null,
        relative_publish_time: review.relative_publish_time ?? null,
      }))
      .slice(0, 6),
    review_source_summary: {
      google_review_count: googleReviewCount,
      expanded_review_count: 0,
      local_snapshot_review_count: localReviewCount,
      analyzed_review_count: mergedPlace.reviews.length,
      displayed_review_count: Math.min(prioritizedReviews.length, 6),
      expanded_reviews_configured: Boolean(process.env.APIFY_TOKEN?.trim()),
      expanded_review_provider: "apify",
      expanded_review_status: process.env.APIFY_TOKEN?.trim() ? "deferred" : "not_configured",
    },
    photos: (place.photos ?? []).map((photo) => ({
      ...photo,
      url: `/api/place-photo?name=${encodeURIComponent(photo.name)}&maxWidthPx=900`,
    })),
    explanation,
    decision_brief: decisionBrief,
    menu,
    recommended_items: recommendedItems,
    community_reviews: [],
  };
}
