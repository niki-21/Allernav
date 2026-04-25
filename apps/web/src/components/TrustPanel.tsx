"use client";

import type { PlaceDetailState, PlaceSummary } from "@/lib/types";

import ScoreBadge from "./ScoreBadge";

interface TrustPanelProps {
  place: PlaceSummary | null;
  detailState: PlaceDetailState | undefined;
  onRetry: () => void;
}

export default function TrustPanel({
  place,
  detailState,
  onRetry,
}: TrustPanelProps) {
  if (!place) {
    return (
      <div className="trust-panel-empty">
        <p className="panel-eyebrow">Trust View</p>
        <h2>Select a place to inspect its allergy evidence.</h2>
        <p>
          AllerNav turns restaurant reviews into an evidence-backed brief so you can compare nearby options quickly.
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
  const reviewSignalCount = data.evidence.length;
  const signalSource =
    reviewSignalCount > 0 && data.menu
      ? `${reviewSignalCount} review signal${reviewSignalCount === 1 ? "" : "s"} + local menu snapshot`
      : reviewSignalCount > 0
        ? `${reviewSignalCount} review signal${reviewSignalCount === 1 ? "" : "s"}`
        : data.menu
          ? "Local menu snapshot only"
          : "Very limited signal";

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

      <div className="decision-brief-card">
        <p className="detail-section-title">AI Read</p>
        <h3 className="decision-brief-headline">{data.decision_brief.headline}</h3>
        <p className="trust-explanation">{data.decision_brief.summary}</p>
        <p className="panel-note">Based on {signalSource}</p>
        <div className="action-callout">
          <strong>Takeaway</strong>
          <p>{data.decision_brief.recommended_action}</p>
        </div>
        <p className="panel-note">
          Current confidence {Math.round(data.score_summary.evidence_confidence * 100)}% ·{" "}
          {data.score_summary.evidence_summary}
        </p>
      </div>

      <div className="detail-action-row">
        <a className="detail-link" href={data.google_maps_uri} target="_blank" rel="noreferrer">
          View on Google Maps
        </a>
        <a className="detail-link primary" href={data.google_review_uri} target="_blank" rel="noreferrer">
          Write on Google
        </a>
      </div>

      {data.recommended_items.length > 0 && (
        <div className="detail-section">
          <p className="detail-section-title">Best Items To Verify</p>
          <div className="menu-section-list">
            {data.recommended_items.slice(0, 2).map((item) => (
              <article key={`${item.section_title ?? "pick"}-${item.name}`} className="menu-card recommended">
                <div className="menu-card-header">
                  <strong>{item.name}</strong>
                  <span className="signal-pill neutral">{item.source === "llm" ? "AI pick" : "Smart pick"}</span>
                </div>
                <p className="menu-card-body">{item.reason}</p>
                {item.caution && item.caution.trim().length > 0 && <p className="menu-card-note">{item.caution}</p>}
              </article>
            ))}
          </div>
        </div>
      )}

      <div className="detail-section">
        <p className="detail-section-title">What Reviews Say</p>
        <div className="evidence-list compact">
          {data.evidence.length === 0 && (
            <article className="evidence-item empty">
              <p className="evidence-excerpt">No allergy-specific review quotes were found for this place yet.</p>
            </article>
          )}

          {data.evidence.slice(0, 2).map((item) => {
            return (
              <article key={`${item.review_id}-${item.signal_type}-${item.matched_phrase}`} className={`evidence-item ${item.impact}`}>
                <div className="evidence-item-header">
                  <span>{item.author_name ?? "Google review"}</span>
                  <span>{item.rating ? `${item.rating.toFixed(1)}★` : "Rating unavailable"}</span>
                </div>
                <p className="evidence-excerpt">{item.excerpt}</p>
              </article>
            );
          })}
        </div>
      </div>
    </div>
  );
}
