import type { PlaceDetailState, PlaceDetailsResponse } from "./types";

export function seedPlaceDetailsState(placeIds: string[]): Record<string, PlaceDetailState> {
  return Object.fromEntries(placeIds.map((id) => [id, { status: "loading" } satisfies PlaceDetailState]));
}

export function applyPlaceDetailSuccess(
  current: Record<string, PlaceDetailState>,
  placeId: string,
  data: PlaceDetailsResponse,
): Record<string, PlaceDetailState> {
  return {
    ...current,
    [placeId]: { status: "ready", data },
  };
}

export function applyPlaceDetailError(
  current: Record<string, PlaceDetailState>,
  placeId: string,
  message: string,
): Record<string, PlaceDetailState> {
  return {
    ...current,
    [placeId]: { status: "error", message },
  };
}
