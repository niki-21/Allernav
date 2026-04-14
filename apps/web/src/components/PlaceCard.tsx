import ScoreBadge from "@/components/ScoreBadge";
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

export default function PlaceCard({ place, detailState, selected, onSelect }: PlaceCardProps) {
  const isReady = detailState?.status === "ready";
  const isLoading = !detailState || detailState.status === "loading";

  return (
    <button type="button" className={`place-card ${selected ? "selected" : ""}`} onClick={onSelect}>
      <div className="place-card-header">
        <div>
          <p className="place-card-title">{place.name}</p>
          <p className="place-card-address">{place.address ?? "Address unavailable"}</p>
        </div>
        {isReady ? (
          <ScoreBadge summary={detailState.data.score_summary} />
        ) : (
          <div className="card-score-skeleton" />
        )}
      </div>

      <p className="place-card-meta">{formatRating(place.rating, place.user_rating_count)}</p>

      {isLoading && (
        <div className="place-card-loading">
          <div className="skeleton skeleton-line" />
          <div className="skeleton skeleton-line short" />
        </div>
      )}

      {detailState?.status === "error" && <p className="place-card-error">Scoring unavailable right now.</p>}

      {isReady && (
        <>
          <p className="place-card-meta">
            {detailState.data.score_summary.evidence_count} review signals · confidence{" "}
            {Math.round(detailState.data.score_summary.confidence * 100)}%
          </p>
          <div className="signal-list">
            {detailState.data.score_summary.positive_signals.slice(0, 2).map((signal) => (
              <span key={signal} className="signal-pill positive">
                {signal}
              </span>
            ))}
            {detailState.data.score_summary.negative_signals.slice(0, 2).map((signal) => (
              <span key={signal} className="signal-pill negative">
                {signal}
              </span>
            ))}
          </div>
        </>
      )}
    </button>
  );
}

