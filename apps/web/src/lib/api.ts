import type {
  AgentRecommendationResult,
  AllergyTag,
  AskRestaurantResponse,
  LatLng,
  MenuRefreshJob,
  NearbySuggestionResponse,
  PlaceDetailsResponse,
  ReviewRefreshJob,
  SearchResponse,
} from "./types";

const API_PREFIX = (process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "") + "/api";

export function buildSearchPayload(query: string, center: LatLng, allergens: AllergyTag[]) {
  return {
    query,
    center,
    allergens,
  };
}

export function buildMenuRefreshPayload(context: { placeName?: string | null; websiteUrl?: string | null }) {
  return {
    restaurant_name: context.placeName ?? null,
    website_url: context.websiteUrl ?? null,
  };
}

export function buildNearbySuggestionPayload(
  question: string,
  center: LatLng,
  allergens: AllergyTag[],
  candidatePlaceIds: string[],
) {
  const useVisibleCandidates = shouldUseVisibleCandidates(question);
  const candidates = useVisibleCandidates ? candidatePlaceIds : [];
  return {
    question,
    query: question,
    center,
    allergens,
    candidate_place_ids: candidates,
    max_places: Math.min(8, Math.max(1, candidates.length || 6)),
    top_evidence: 3,
  };
}

export function shouldUseVisibleCandidates(question: string): boolean {
  const text = question.toLowerCase();
  const freshSearchTerms = [
    "bagel",
    "bakery",
    "breakfast",
    "brunch",
    "burger",
    "cafe",
    "chinese",
    "deli",
    "ethiopian",
    "french",
    "gluten free",
    "indian",
    "italian",
    "japanese",
    "korean",
    "mediterranean",
    "mexican",
    "pizza",
    "ramen",
    "sushi",
    "thai",
    "vegan",
    "vegetarian",
  ];
  return !freshSearchTerms.some((term) => text.includes(term));
}

export function buildPlaceDetailsUrl(placeId: string, allergens: AllergyTag[]): string {
  const params = new URLSearchParams();
  allergens.forEach((allergen) => params.append("allergens", allergen));
  const queryString = params.toString();
  return `${API_PREFIX}/places/${encodeURIComponent(placeId)}${queryString ? `?${queryString}` : ""}`;
}

export async function searchPlaces(query: string, center: LatLng, allergens: AllergyTag[]): Promise<SearchResponse> {
  const response = await fetch(`${API_PREFIX}/search`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(buildSearchPayload(query, center, allergens)),
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return (await response.json()) as SearchResponse;
}

export async function fetchPlaceDetails(placeId: string, allergens: AllergyTag[]): Promise<PlaceDetailsResponse> {
  const response = await fetch(buildPlaceDetailsUrl(placeId, allergens));
  if (!response.ok) {
    throw new Error(await response.text());
  }

  return (await response.json()) as PlaceDetailsResponse;
}

export async function refreshPlaceMenu(
  placeId: string,
  context: { placeName?: string | null; websiteUrl?: string | null } = {},
): Promise<MenuRefreshJob> {
  const response = await fetch(`${API_PREFIX}/places/${encodeURIComponent(placeId)}/menu-refresh`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(buildMenuRefreshPayload(context)),
    signal: AbortSignal.timeout(55_000),
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string; message?: string } | null;
    throw new Error(body?.message ?? body?.detail ?? `Menu refresh failed with status ${response.status}.`);
  }
  return (await response.json()) as MenuRefreshJob;
}

export async function fetchMenuRefreshJob(jobId: string): Promise<MenuRefreshJob> {
  const response = await fetch(`${API_PREFIX}/menu-refresh-jobs/${encodeURIComponent(jobId)}`, {
    cache: "no-store",
    signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok) {
    throw new Error(`Menu refresh status failed with status ${response.status}.`);
  }
  return (await response.json()) as MenuRefreshJob;
}

export async function refreshPlaceReviews(placeId: string): Promise<ReviewRefreshJob> {
  const response = await fetch(`${API_PREFIX}/places/${encodeURIComponent(placeId)}/reviews-refresh`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return (await response.json()) as ReviewRefreshJob;
}

export async function askRestaurant(
  placeId: string,
  placeName: string,
  allergens: AllergyTag[],
): Promise<AskRestaurantResponse> {
  const response = await fetch(`${API_PREFIX}/places/${encodeURIComponent(placeId)}/ask`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      place_id: placeId,
      place_name: placeName,
      allergens,
    }),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return (await response.json()) as AskRestaurantResponse;
}

export async function askNearbyPlaces(
  question: string,
  center: LatLng,
  allergens: AllergyTag[],
  candidatePlaceIds: string[],
): Promise<NearbySuggestionResponse> {
  const response = await fetch(`${API_PREFIX}/rag/nearby-suggestions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(buildNearbySuggestionPayload(question, center, allergens, candidatePlaceIds)),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return (await response.json()) as NearbySuggestionResponse;
}

export async function analyzeRestaurant(
  placeId: string,
  placeName: string,
  allergens: AllergyTag[],
  websiteUrl?: string | null,
): Promise<AgentRecommendationResult> {
  const response = await fetch(`${API_PREFIX}/analyze-restaurant`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      restaurant_id: placeId,
      restaurant_name: placeName,
      website_url: websiteUrl ?? null,
      profile: {
        allergens,
        sensitivity: "careful",
        prep_preference: "verify",
      },
    }),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return (await response.json()) as AgentRecommendationResult;
}
