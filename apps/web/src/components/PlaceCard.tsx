import { forwardRef } from "react";

import type { PlaceDetailState, PlaceSummary } from "@/lib/types";

interface PlaceCardProps {
  place: PlaceSummary;
  detailState: PlaceDetailState | undefined;
  selected: boolean;
  onSelect: () => void;
}

function formatRating(rating?: number | null, count?: number | null): string {
  if (!rating) {
    return "Google rating unavailable";
  }
  if (!count) {
    return `${rating.toFixed(1)} Google rating`;
  }
  return `${rating.toFixed(1)} on Google · ${count.toLocaleString()} reviews`;
}

const PlaceCard = forwardRef<HTMLButtonElement, PlaceCardProps>(function PlaceCard(
  { place, detailState, selected, onSelect },
  ref,
) {
  const isReady = detailState?.status === "ready";
  const displayPlace = isReady ? detailState.data : place;

  return (
    <button ref={ref} type="button" className={`place-card ${selected ? "selected" : ""}`} onClick={onSelect}>
      <p className="place-card-title">{displayPlace.name}</p>
      <p className="place-card-address">{displayPlace.address ?? "Address unavailable"}</p>

      <p className="place-card-meta">{formatRating(displayPlace.rating, displayPlace.user_rating_count)}</p>

      {detailState?.status === "error" && <p className="place-card-error">Details unavailable right now.</p>}

      {isReady && <p className="place-card-meta">Evidence score {detailState.data.score_summary.fit_score}/100 · verify menu</p>}
    </button>
  );
});

export default PlaceCard;
