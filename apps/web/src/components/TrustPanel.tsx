import { formatAllergenLabel } from "@/lib/allergens";
import type { AllergyTag, PlaceDetailState, PlaceSummary } from "@/lib/types";

import ScoreBadge from "./ScoreBadge";

interface TrustPanelProps {
  place: PlaceSummary | null;
  detailState: PlaceDetailState | undefined;
  selectedAllergens: AllergyTag[];
  onRetry: () => void;
}

export default function TrustPanel({
  place,
  detailState,
  selectedAllergens,
  onRetry,
}: TrustPanelProps) {
  if (!place) {
    return (
      <div className="trust-panel-empty">
        <p className="panel-eyebrow">Trust View</p>
        <h2>Select a place to inspect its allergy evidence.</h2>
        <p>
          Allernav reads review language, then surfaces concrete quotes that help explain whether a spot feels safer
          or riskier for your selected profile.
        </p>
      </div>
    );
  }

  if (!detailState || detailState.status === "loading") {
    return (
      <div className="trust-panel-loading">
        <p className="panel-eyebrow">Trust View</p>
        <h2>{place.name}</h2>
        <div className="skeleton skeleton-badge" />
        <div className="skeleton skeleton-line" />
        <div className="skeleton skeleton-line" />
        <div className="skeleton skeleton-review" />
        <div className="skeleton skeleton-review" />
      </div>
    );
  }

  if (detailState.status === "error") {
    return (
      <div className="trust-panel-empty">
        <p className="panel-eyebrow">Trust View</p>
        <h2>{place.name}</h2>
        <p>{detailState.message}</p>
        <button type="button" className="retry-button" onClick={onRetry}>
          Retry scoring
        </button>
      </div>
    );
  }

  const { data } = detailState;

  return (
    <div className="trust-panel-content">
      <p className="panel-eyebrow">Trust View</p>
      <div className="trust-panel-heading">
        <div>
          <h2>{data.name}</h2>
          <p>{data.address ?? "Address unavailable"}</p>
        </div>
        <ScoreBadge summary={data.score_summary} />
      </div>

      <div className="detail-pill-row">
        <span className="detail-pill">Profile: {selectedAllergens.map(formatAllergenLabel).join(", ")}</span>
        <span className="detail-pill">
          Confidence {Math.round(data.score_summary.confidence * 100)}% · {data.score_summary.evidence_count} signals
        </span>
      </div>

      <p className="trust-explanation">{data.explanation}</p>

      {data.editorial_summary && (
        <div className="detail-section">
          <p className="detail-section-title">Place Snapshot</p>
          <p>{data.editorial_summary}</p>
        </div>
      )}

      <div className="detail-section">
        <p className="detail-section-title">Evidence From Reviews</p>
        <div className="evidence-list">
          {data.evidence.map((item) => (
            <article key={`${item.review_id}-${item.signal_type}`} className={`evidence-item ${item.impact}`}>
              <div className="evidence-item-header">
                <span>{item.author_name ?? "Google review"}</span>
                <span>{item.rating ? `${item.rating.toFixed(1)}★` : "Rating unavailable"}</span>
              </div>
              <p className="evidence-excerpt">{item.excerpt}</p>
              <div className="signal-list">
                <span className={`signal-pill ${item.impact}`}>
                  {item.impact === "positive" ? "Reassuring" : "Risk note"}
                </span>
                {item.matched_allergens.map((allergen) => (
                  <span key={`${item.review_id}-${allergen}`} className="signal-pill neutral">
                    {formatAllergenLabel(allergen)}
                  </span>
                ))}
              </div>
            </article>
          ))}
        </div>
      </div>
    </div>
  );
}

