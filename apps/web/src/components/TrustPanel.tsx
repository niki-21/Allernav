"use client";

import Image from "next/image";
import { useState } from "react";

import type { AskRestaurantResponse, MenuRefreshJob, PlaceDetailState, PlaceSummary } from "@/lib/types";

interface TrustPanelProps {
  place: PlaceSummary | null;
  detailState: PlaceDetailState | undefined;
  onRetry: () => void;
  onRefreshMenu: () => void;
  onAskRestaurant: () => void;
  menuRefreshJob?: MenuRefreshJob | null;
  askResponse?: AskRestaurantResponse | null;
  isRefreshingMenu?: boolean;
  isAskingRestaurant?: boolean;
}

type PlaceTab = "overview" | "menu" | "reviews" | "about";

function formatRiskLabel(value: string): string {
  return value.replace(/_/g, " ");
}

export default function TrustPanel({
  place,
  detailState,
  onRetry,
  onRefreshMenu,
  onAskRestaurant,
  menuRefreshJob,
  askResponse,
  isRefreshingMenu = false,
  isAskingRestaurant = false,
}: TrustPanelProps) {
  const [tabState, setTabState] = useState<{ placeId: string | null; tab: PlaceTab }>({
    placeId: null,
    tab: "overview",
  });

  if (!place) {
    return (
      <div className="trust-panel-empty">
        <p className="panel-eyebrow">Place details</p>
        <h2>Select a restaurant</h2>
        <p>Click a map marker or search result to review allergy evidence and menu signals.</p>
      </div>
    );
  }

  if (!detailState || detailState.status === "loading" || detailState.status === "idle") {
    return (
      <div className="trust-panel-loading">
        <p className="panel-eyebrow">Place details</p>
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
        <p className="panel-eyebrow">Place details</p>
        <h2>{place.name}</h2>
        <p>{detailState.message}</p>
        <button type="button" className="retry-button" onClick={onRetry}>
          Retry scoring
        </button>
      </div>
    );
  }

  const { data } = detailState;
  const activeTab = tabState.placeId === data.id ? tabState.tab : "overview";
  const menuSections = data.menu?.sections ?? [];
  const menuItemCount = menuSections.reduce((count, section) => count + section.items.length, 0);
  const reviewSnippets = data.review_snippets ?? [];
  const photos = data.photos ?? [];
  const reviewSignalCount = data.evidence.length;
  const signalSource =
    reviewSignalCount > 0 && data.menu
      ? `${reviewSignalCount} review signal${reviewSignalCount === 1 ? "" : "s"} + local menu snapshot`
      : reviewSignalCount > 0
        ? `${reviewSignalCount} review signal${reviewSignalCount === 1 ? "" : "s"}`
        : data.menu
          ? "Local menu snapshot only"
          : "Very limited signal";
  const confidencePercent = Math.round(data.score_summary.evidence_confidence * 100);
  const agentRecommendation = data.agent_recommendation ?? null;
  const agentConfidencePercent = agentRecommendation ? Math.round(agentRecommendation.confidence * 100) : null;
  const menuStatus = isRefreshingMenu ? "running" : menuRefreshJob?.status;
  const refreshLabel =
    menuStatus === "queued"
      ? "Queued"
      : menuStatus === "running"
        ? "Scanning"
        : menuStatus === "complete"
          ? "Re-scan source"
          : "Re-scan menu source";

  return (
    <div className="trust-panel-content">
      {photos.length > 0 && (
        <div className="place-photo-strip" aria-label="Place photos">
          {photos.slice(0, 4).map((photo, index) => (
            <Image
              key={photo.name}
              src={photo.url}
              alt={`${data.name} photo ${index + 1}`}
              width={180}
              height={96}
              loading="lazy"
            />
          ))}
        </div>
      )}

      <div className="place-sheet-header">
        <p className="panel-eyebrow">Place details</p>
        <h2>{data.name}</h2>
        <p>{data.address ?? "Address unavailable"}</p>
        <p className="compact-score-row">
          Allergy fit {data.score_summary.fit_score} · {confidencePercent}% confidence · verify before ordering
        </p>
      </div>

      <div className="detail-action-row compact-actions">
        <a className="detail-link google-link" href={data.google_maps_uri} target="_blank" rel="noreferrer">
          View on Google Maps
        </a>
        <button type="button" className="detail-link" onClick={onRefreshMenu} disabled={isRefreshingMenu}>
          <span className={isRefreshingMenu ? "refresh-spinner active" : "refresh-spinner"} />
          {refreshLabel}
        </button>
      </div>

      <div className="place-tabs" role="tablist" aria-label="Place information">
        {(["overview", "menu", "reviews", "about"] as PlaceTab[]).map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={activeTab === tab}
            className={`place-tab ${activeTab === tab ? "active" : ""}`}
            onClick={() => setTabState({ placeId: data.id, tab })}
          >
            {tab}
          </button>
        ))}
      </div>

      {activeTab === "overview" && (
        <div className="place-tab-panel">
          <div className="overview-line">
            <strong>{data.decision_brief.headline}</strong>
            <p>{data.decision_brief.summary}</p>
          </div>
          {agentRecommendation && (
            <div className={`overview-line agent-risk ${agentRecommendation.overall_risk}`}>
              <strong>
                Agentic risk: {formatRiskLabel(agentRecommendation.overall_risk)} ·{" "}
                {formatRiskLabel(agentRecommendation.recommended_action)}
              </strong>
              <p>{agentRecommendation.summary}</p>
              {agentConfidencePercent !== null && <p>{agentConfidencePercent}% source confidence.</p>}
            </div>
          )}
          {agentRecommendation && agentRecommendation.missing_information.length > 0 && (
            <div className="overview-line">
              <strong>Missing information</strong>
              <p>{agentRecommendation.missing_information.slice(0, 2).join(" ")}</p>
            </div>
          )}
          {agentRecommendation && agentRecommendation.recommended_questions.length > 0 && (
            <div className="overview-line">
              <strong>Questions for staff</strong>
              <p>{agentRecommendation.recommended_questions.slice(0, 2).join(" ")}</p>
            </div>
          )}
          {photos.length > 0 && (
            <div className="overview-line">
              <strong>Photos</strong>
              <p>{photos.length} Google place photo{photos.length === 1 ? "" : "s"} available for quick context.</p>
            </div>
          )}
          <div className="overview-line">
            <strong>Menu</strong>
            <p>
              {menuItemCount > 0
                ? `${menuItemCount} menu item${menuItemCount === 1 ? "" : "s"} captured from ${data.menu?.source_url ?? "available sources"}.`
                : "AllerNav checks official menu sources when a restaurant website is available. Re-scan only if the source looks stale or incomplete."}
            </p>
          </div>
          {menuRefreshJob && <p className="menu-job-note">{menuRefreshJob.message}</p>}
        </div>
      )}

      {activeTab === "menu" && (
        <div className="place-tab-panel">
          <div className="menu-source-row">
            <div>
              <strong>Menu</strong>
              <p>
                {menuItemCount > 0
                  ? `${menuItemCount} menu item${menuItemCount === 1 ? "" : "s"} found. Inferred items are never labeled safe.`
                  : "No reliable menu items extracted yet."}
              </p>
            </div>
            {data.menu?.source_url && (
              <a className="source-link" href={data.menu.source_url} target="_blank" rel="noreferrer">
                Source
              </a>
            )}
          </div>

          {menuRefreshJob && <p className="menu-job-note">{menuRefreshJob.message}</p>}

          {menuSections.length > 0 ? (
            <div className="menu-section-list google-menu-list">
              {menuSections.slice(0, 3).map((section) => (
                <section key={section.title} className="menu-list-section">
                  <h3>{section.title}</h3>
                  {section.items.slice(0, 6).map((item) => (
                    <article key={`${section.title}-${item.name}`} className="menu-list-item">
                      <strong>{item.name}</strong>
                      {item.price && <span>{item.price}</span>}
                      {item.description && <p>{item.description}</p>}
                      {item.likely_risky_for.some((allergen) => data.selected_allergens.includes(allergen)) && (
                        <p className="menu-risk-note">
                          Flags:{" "}
                          {item.likely_risky_for
                            .filter((allergen) => data.selected_allergens.includes(allergen))
                            .map((allergen) => allergen.replace("_", " "))
                            .join(", ")}
                        </p>
                      )}
                    </article>
                  ))}
                </section>
              ))}
            </div>
          ) : (
            <article className="empty-menu-state">
              <strong>Get menu information</strong>
              <p>
                AllerNav checks compliant public sources for the selected restaurant: the restaurant website, linked menu
                or ordering pages, PDFs, and accessible menu images. Re-scan if the source looks stale or incomplete.
              </p>
              {data.website_uri && (
                <a className="source-link" href={data.website_uri} target="_blank" rel="noreferrer">
                  Restaurant website
                </a>
              )}
            </article>
          )}

          {data.recommended_items.length > 0 && (
            <div className="menu-section-list compact-recommendations">
              <strong>Items to verify</strong>
              {data.recommended_items.slice(0, 2).map((item) => (
                <article key={`${item.section_title ?? "pick"}-${item.name}`} className="menu-list-item">
                  <strong>{item.name}</strong>
                  <p>{item.reason}</p>
                  <p>{item.caution || "Verify ingredients and prep before ordering."}</p>
                </article>
              ))}
            </div>
          )}

          {agentRecommendation && agentRecommendation.dish_results.length > 0 && (
            <div className="menu-section-list compact-recommendations">
              <strong>Agent dish risk</strong>
              {agentRecommendation.dish_results.slice(0, 3).map((item) => (
                <article key={`${item.dish}-${item.risk_level}`} className="menu-list-item">
                  <strong>{item.dish}</strong>
                  <p>
                    {formatRiskLabel(item.risk_level)} · {Math.round(item.confidence * 100)}% confidence
                  </p>
                  {item.detected_allergens.length > 0 && (
                    <p>Flags: {item.detected_allergens.map((allergen) => allergen.replace("_", " ")).join(", ")}</p>
                  )}
                </article>
              ))}
            </div>
          )}

          <button type="button" className="ask-button" onClick={onAskRestaurant} disabled={isAskingRestaurant}>
            {isAskingRestaurant ? "Saving question..." : "Ask restaurant to verify"}
          </button>
          {askResponse && <p className="menu-job-note">{askResponse.suggested_script}</p>}
        </div>
      )}

      {activeTab === "reviews" && (
        <div className="place-tab-panel">
          <p className="panel-note">{signalSource}</p>

          <div className="review-group">
            <strong>Allergy evidence</strong>
            <div className="evidence-list compact">
              {data.evidence.length === 0 && (
                <article className="evidence-item empty">
                  <p className="evidence-excerpt">No allergy-specific review quotes were found for this place yet.</p>
                </article>
              )}

              {data.evidence.slice(0, 4).map((item) => {
                return (
                  <article
                    key={`${item.review_id}-${item.signal_type}-${item.matched_phrase}`}
                    className={`evidence-item ${item.impact}`}
                  >
                    <div className="evidence-item-header">
                      <span>{item.author_name ?? "Google review"}</span>
                      <span>{item.rating ? `${item.rating.toFixed(1)}★` : "Rating unavailable"}</span>
                    </div>
                    <p className="evidence-excerpt">{item.excerpt}</p>
                    <p className="review-source-line">
                      Matched {item.signal_label.toLowerCase()} · {item.matched_allergens.map((allergen) => allergen.replace("_", " ")).join(", ")}
                    </p>
                  </article>
                );
              })}
            </div>
          </div>

          {agentRecommendation && agentRecommendation.evidence.length > 0 && (
            <div className="review-group">
              <strong>Menu evidence</strong>
              <div className="evidence-list compact">
                {agentRecommendation.evidence.slice(0, 4).map((item) => (
                  <article key={item.id} className="evidence-item">
                    <div className="evidence-item-header">
                      <span>{item.dish_name ?? "Menu source"}</span>
                      <span>{formatRiskLabel(item.source_type)}</span>
                    </div>
                    <p className="evidence-excerpt">{item.text}</p>
                    {item.matched_allergens.length > 0 && (
                      <p className="review-source-line">
                        Matched {item.matched_allergens.map((allergen) => allergen.replace("_", " ")).join(", ")}
                      </p>
                    )}
                  </article>
                ))}
              </div>
            </div>
          )}

          <div className="review-group">
            <strong>Recent Google reviews</strong>
            <div className="evidence-list compact">
              {reviewSnippets.length === 0 && (
                <article className="evidence-item empty">
                  <p className="evidence-excerpt">Google review text was not returned for this place.</p>
                </article>
              )}

              {reviewSnippets.slice(0, 4).map((review) => (
                <article key={review.review_id} className="evidence-item">
                  <div className="evidence-item-header">
                    <span>{review.author_name ?? "Google review"}</span>
                    <span>{review.rating ? `${review.rating.toFixed(1)}★` : review.relative_publish_time ?? "Review"}</span>
                  </div>
                  <p className="evidence-excerpt">{review.text}</p>
                  {review.relative_publish_time && <p className="review-source-line">{review.relative_publish_time}</p>}
                </article>
              ))}
            </div>
          </div>
        </div>
      )}

      {activeTab === "about" && (
        <div className="place-tab-panel">
          <div className="overview-line">
            <strong>Allergy read</strong>
            <p>{data.score_summary.evidence_summary}</p>
          </div>
          <div className="overview-line">
            <strong>Confidence</strong>
            <p>{confidencePercent}% · {signalSource}</p>
          </div>
          <div className="overview-line">
            <strong>Safety note</strong>
            <p>Use inferred information cautiously and verify ingredients, prep surfaces, and cross-contact before ordering.</p>
          </div>
          {agentRecommendation && (
            <div className="overview-line">
              <strong>Agent trace</strong>
              <p>{agentRecommendation.trace.nodes.join(" -> ")}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
