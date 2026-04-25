import type { LatLng, PlaceDetailState, PlaceSummary } from "./types";

function toRadians(value: number): number {
  return (value * Math.PI) / 180;
}

export function distanceInMiles(a: LatLng, b: LatLng): number {
  const earthRadiusMiles = 3958.8;
  const latDelta = toRadians(b.lat - a.lat);
  const lngDelta = toRadians(b.lng - a.lng);
  const latA = toRadians(a.lat);
  const latB = toRadians(b.lat);

  const haversine =
    Math.sin(latDelta / 2) ** 2 + Math.cos(latA) * Math.cos(latB) * Math.sin(lngDelta / 2) ** 2;

  return 2 * earthRadiusMiles * Math.asin(Math.sqrt(haversine));
}

export function shouldShowSearchAreaButton(searchCenter: LatLng, mapCenter: LatLng): boolean {
  return distanceInMiles(searchCenter, mapCenter) >= 0.3;
}

function getDetailSortValue(place: PlaceSummary, detailState: PlaceDetailState | undefined) {
  if (!detailState || detailState.status !== "ready") {
    return {
      ready: 0,
      meaningfulEvidence: 0,
      fitScore: -1,
      evidenceConfidence: -1,
      evidenceCount: -1,
      rating: place.rating ?? -1,
    };
  }

  return {
    ready: 1,
    meaningfulEvidence: detailState.data.score_summary.meaningful_evidence ? 1 : 0,
    fitScore: detailState.data.score_summary.fit_score,
    evidenceConfidence: detailState.data.score_summary.evidence_confidence,
    evidenceCount: detailState.data.score_summary.evidence_count,
    rating: place.rating ?? -1,
  };
}

export function rankPlaces(
  places: PlaceSummary[],
  detailStates: Record<string, PlaceDetailState>,
): PlaceSummary[] {
  const originalOrder = new Map(places.map((place, index) => [place.id, index]));

  return [...places].sort((left, right) => {
    const leftValue = getDetailSortValue(left, detailStates[left.id]);
    const rightValue = getDetailSortValue(right, detailStates[right.id]);

    return (
      rightValue.ready - leftValue.ready ||
      rightValue.meaningfulEvidence - leftValue.meaningfulEvidence ||
      rightValue.fitScore - leftValue.fitScore ||
      rightValue.evidenceConfidence - leftValue.evidenceConfidence ||
      rightValue.evidenceCount - leftValue.evidenceCount ||
      rightValue.rating - leftValue.rating ||
      (originalOrder.get(left.id) ?? 0) - (originalOrder.get(right.id) ?? 0)
    );
  });
}
