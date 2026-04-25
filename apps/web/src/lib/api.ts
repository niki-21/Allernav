import type { AllergyTag, LatLng, PlaceDetailsResponse, SearchResponse } from "./types";

const API_PREFIX = "/api";

export function buildSearchPayload(query: string, center: LatLng, allergens: AllergyTag[]) {
  return {
    query,
    center,
    allergens,
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
