import type { AllergyTag, LatLng, PlaceDetailsResponse, SearchResponse } from "./types";

export function getApiBaseUrl(): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || "http://localhost:8000";
  return baseUrl.endsWith("/") ? baseUrl.slice(0, -1) : baseUrl;
}

export function buildSearchPayload(query: string, center: LatLng, allergens: AllergyTag[]) {
  return {
    query,
    center,
    allergens,
  };
}

export function buildPlaceDetailsUrl(baseUrl: string, placeId: string, allergens: AllergyTag[]): string {
  const params = new URLSearchParams();
  allergens.forEach((allergen) => params.append("allergens", allergen));
  const queryString = params.toString();
  return `${baseUrl}/api/places/${encodeURIComponent(placeId)}${queryString ? `?${queryString}` : ""}`;
}

export async function searchPlaces(query: string, center: LatLng, allergens: AllergyTag[]): Promise<SearchResponse> {
  const response = await fetch(`${getApiBaseUrl()}/api/search`, {
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
  const response = await fetch(buildPlaceDetailsUrl(getApiBaseUrl(), placeId, allergens));
  if (!response.ok) {
    throw new Error(await response.text());
  }

  return (await response.json()) as PlaceDetailsResponse;
}
