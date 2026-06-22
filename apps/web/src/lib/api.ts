import type {
  AgentRecommendationResult,
  AllergyTag,
  AskRestaurantResponse,
  LatLng,
  MenuRefreshJob,
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
  });
  if (!response.ok) {
    throw new Error(await response.text());
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

export async function analyzeRestaurant(
  placeId: string,
  placeName: string,
  allergens: AllergyTag[],
): Promise<AgentRecommendationResult> {
  const response = await fetch(`${API_PREFIX}/analyze-restaurant`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      restaurant_id: placeId,
      restaurant_name: placeName,
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
