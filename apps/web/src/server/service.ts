import { ALLERGEN_OPTIONS } from "../lib/allergens.ts";
import type { AllergyTag, LatLng, PlaceDetailsResponse, PlaceMenu, PlaceScoreSummary, PlaceSummary, SearchResponse } from "../lib/types.ts";
import { buildDecisionBrief } from "./briefing.ts";
import { GooglePlacesClient, type GooglePlaceDetails } from "./googlePlaces.ts";
import { getLocalPlaceSnapshot } from "./localPlaceSnapshots.ts";
import { recommendMenuItems } from "./recommendations.ts";
import { analyzePlace } from "./scoring.ts";

export const DEFAULT_CENTER: LatLng = { lat: 40.741895, lng: -73.989308 };

const ALLERGY_TAGS = new Set<AllergyTag>(ALLERGEN_OPTIONS.map((option) => option.value));

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

function buildMenuEvidenceSummary(
  riskyCount: number,
  recommendedCount: number,
  sharedPrepCount: number,
): string {
  if (riskyCount >= Math.max(3, recommendedCount + 2) || sharedPrepCount >= 2) {
    return "Menu snapshot leans risky for selected allergens";
  }
  if (recommendedCount >= 2) {
    return "Menu snapshot shows a few lower-risk options";
  }
  if (recommendedCount === 1) {
    return "Menu snapshot shows one simpler option";
  }
  if (riskyCount > 0) {
    return "Menu snapshot is mixed for selected allergens";
  }
  return "Menu snapshot only";
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
  const selectedAllergens = allergens.length > 0 ? allergens : ["peanut"];
  const place = await client.getPlaceDetails(placeId);
  const localSnapshot = getLocalPlaceSnapshot(place.name);
  const mergedPlace = {
    ...place,
    reviews: [...place.reviews, ...(localSnapshot?.reviews ?? [])],
  };
  const { summary, evidence, explanation } = analyzePlace(mergedPlace, selectedAllergens);
  const menu = localSnapshot?.menu ?? null;
  const recommendedItems = await recommendMenuItems(place.name, selectedAllergens, menu, evidence);
  const scoreSummary = applyMenuSignals(summary, menu, selectedAllergens, recommendedItems.length);
  const decisionBrief = buildDecisionBrief(scoreSummary, evidence, menu, recommendedItems);

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
    google_maps_uri: `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(place.name)}&query_place_id=${encodeURIComponent(place.id)}`,
    google_review_uri: `https://search.google.com/local/writereview?placeid=${encodeURIComponent(place.id)}`,
    selected_allergens: selectedAllergens,
    score_summary: scoreSummary,
    evidence,
    review_snippets: mergedPlace.reviews
      .filter((review) => review.text.trim().length > 0)
      .slice(0, 5)
      .map((review) => ({
        review_id: review.review_id,
        author_name: review.author_name ?? null,
        rating: review.rating ?? null,
        text: review.text,
        publish_time: review.publish_time ?? null,
        relative_publish_time: review.relative_publish_time ?? null,
      })),
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
