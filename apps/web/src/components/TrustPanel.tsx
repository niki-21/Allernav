"use client";

import { useState } from "react";

import type { AskRestaurantResponse, PlaceDetailsResponse, PlaceDetailState, PlaceSummary } from "@/lib/types";

interface TrustPanelProps {
  place: PlaceSummary | null;
  detailState: PlaceDetailState | undefined;
  onRetry: () => void;
  onAskRestaurant: () => void;
  askResponse?: AskRestaurantResponse | null;
  isAskingRestaurant?: boolean;
}

type PlaceTab = "overview" | "menu" | "reviews" | "about";

function formatRiskLabel(value: string): string {
  return value.replace(/_/g, " ");
}

function formatPlaceType(value?: string | null): string {
  if (!value) {
    return "Restaurant";
  }
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatOpenStatus(data: PlaceDetailsResponse): string | null {
  const hours = data.current_opening_hours ?? data.regular_opening_hours;
  if (!hours || typeof hours.openNow !== "boolean") {
    return null;
  }
  return hours.openNow ? "Open now" : "Closed now";
}

function serviceLabels(options: Record<string, boolean | null | undefined> | undefined): string[] {
  const labels: Array<[string, string]> = [
    ["dine_in", "Dine-in"],
    ["takeout", "Takeout"],
    ["delivery", "Delivery"],
    ["reservable", "Reservations"],
    ["serves_lunch", "Lunch"],
    ["serves_dinner", "Dinner"],
    ["serves_vegetarian_food", "Vegetarian options"],
  ];
  return labels.filter(([key]) => options?.[key] === true).map(([, label]) => label);
}

function displayHostName(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function formatAllergenList(values: string[]): string {
  return values.map((value) => value.replace("_", " ")).join(", ");
}

export default function TrustPanel({
  place,
  detailState,
  onRetry,
  askResponse,
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
  const reviewSource = data.review_source_summary;
  const reviewSignalCount = data.evidence.length;
  const signalSource =
    reviewSignalCount > 0
        ? `${reviewSignalCount} allergy signal${reviewSignalCount === 1 ? "" : "s"}`
        : "No allergy-specific review signals";
  const reviewSourceLine = reviewSource?.expanded_review_count
    ? `${reviewSource.expanded_review_count} expanded reviews scanned.`
    : `${reviewSource?.google_review_count ?? reviewSnippets.length} Google review snippets scanned.`;
  const confidencePercent = Math.round(data.score_summary.evidence_confidence * 100);
  const agentRecommendation = data.agent_recommendation ?? null;
  const agentConfidencePercent = agentRecommendation ? Math.round(agentRecommendation.confidence * 100) : null;
  const openStatus = formatOpenStatus(data);
  const services = serviceLabels(data.service_options);
  const ratingLine = [
    data.rating ? `${data.rating.toFixed(1)} on Google` : null,
    data.user_rating_count ? `${data.user_rating_count.toLocaleString()} reviews` : null,
    data.price_range ?? data.price_level?.replace("PRICE_LEVEL_", "").replace(/_/g, " ").toLowerCase() ?? null,
    formatPlaceType(data.primary_type),
  ].filter(Boolean).join(" · ");

  return (
    <div className="trust-panel-content">
      <div className="place-sheet-header">
        <p className="panel-eyebrow">Place details</p>
        <h2>{data.name}</h2>
        <p>{data.address ?? "Address unavailable"}</p>
        {ratingLine && <p>{ratingLine}</p>}
        <p className="compact-score-row">
          Evidence score {data.score_summary.fit_score}/100 · {confidencePercent}% source confidence · verify before ordering
        </p>
      </div>

      <div className="detail-action-row compact-actions">
        <a className="detail-link google-link" href={data.google_maps_uri} target="_blank" rel="noreferrer">
          View on Google Maps
        </a>
        {data.website_uri && (
          <a className="detail-link" href={data.website_uri} target="_blank" rel="noreferrer">
            Website
          </a>
        )}
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
            <strong>{openStatus ?? data.decision_brief.headline}</strong>
            <p>{data.editorial_summary ?? data.decision_brief.summary}</p>
          </div>
          {services.length > 0 && (
            <div className="service-chip-row" aria-label="Service options">
              {services.slice(0, 5).map((service) => (
                <span key={service}>{service}</span>
              ))}
            </div>
          )}
          <div className="overview-line">
            <strong>Allergy read</strong>
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
        </div>
      )}

      {activeTab === "menu" && (
        <div className="place-tab-panel">
          <div className="menu-source-row">
            <div>
              <strong>Menu</strong>
              <p>
                {menuItemCount > 0
                  ? `${menuItemCount} dish-level item${menuItemCount === 1 ? "" : "s"} extracted.`
                  : "No reliable dish-level menu found yet."}
              </p>
            </div>
            {data.menu?.source_url && (
              <a className="source-link" href={data.menu.source_url} target="_blank" rel="noreferrer">
                Source
              </a>
            )}
          </div>
          {menuSections.length > 0 ? (
            <div className="menu-section-list google-menu-list">
              {menuSections.slice(0, 3).map((section) => (
                <section key={section.title} className="menu-list-section">
                  <h3>{section.title}</h3>
                  {section.items.slice(0, 6).map((item) => (
                    (() => {
                      const relevantRisks = item.likely_risky_for.filter((allergen) =>
                        data.selected_allergens.includes(allergen),
                      );
                      return (
                        <article
                          key={`${section.title}-${item.name}`}
                          className={`menu-list-item compact-menu-row ${relevantRisks.length ? "has-risk" : ""}`}
                        >
                          <div>
                            <strong>{item.name}</strong>
                            {relevantRisks.length > 0 && item.description && <p>{item.description}</p>}
                            {relevantRisks.length > 0 && (
                              <p className="menu-risk-note">Flag: {formatAllergenList(relevantRisks)}</p>
                            )}
                          </div>
                          {item.price && <span>{item.price}</span>}
                        </article>
                      );
                    })()
                  ))}
                </section>
              ))}
            </div>
          ) : (
            <article className="empty-menu-state">
              <strong>No reliable dish-level menu found</strong>
              <p>
                AllerNav checked available menu sources but did not find structured dish names with usable ingredient
                context. This is insufficient evidence, not a safety signal.
              </p>
              {data.website_uri && (
                <a className="source-link" href={data.website_uri} target="_blank" rel="noreferrer">
                  Restaurant website
                </a>
              )}
            </article>
          )}

          {askResponse && <p className="menu-job-note">{askResponse.suggested_script}</p>}
        </div>
      )}

      {activeTab === "reviews" && (
        <div className="place-tab-panel">
          <p className="panel-note">{signalSource}</p>
          <p className="panel-note">{reviewSourceLine}</p>

          <div className="review-group">
            <div className="evidence-list compact">
              {data.evidence.length === 0 && (
                <article className="evidence-item empty">
                  <p className="evidence-excerpt">No allergy-specific review signals found.</p>
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
        </div>
      )}

      {activeTab === "about" && (
        <div className="place-tab-panel">
          {data.address && (
            <div className="about-row">
              <strong>Address</strong>
              <p>{data.address}</p>
            </div>
          )}
          {openStatus && (
            <div className="about-row">
              <strong>Hours</strong>
              <p>{openStatus}</p>
              {(data.current_opening_hours?.weekdayDescriptions ?? data.regular_opening_hours?.weekdayDescriptions ?? [])
                .slice(0, 7)
                .map((line) => (
                  <p key={line}>{line}</p>
                ))}
            </div>
          )}
          {(data.national_phone_number || data.international_phone_number) && (
            <div className="about-row">
              <strong>Phone</strong>
              <p>{data.national_phone_number ?? data.international_phone_number}</p>
            </div>
          )}
          {data.website_uri && (
            <div className="about-row">
              <strong>Website</strong>
              <a className="source-link" href={data.website_uri} target="_blank" rel="noreferrer">
                {displayHostName(data.website_uri)}
              </a>
            </div>
          )}
          <div className="about-row">
            <strong>Safety note</strong>
            <p>Use inferred information cautiously and verify ingredients, prep surfaces, and cross-contact before ordering.</p>
          </div>
          {agentRecommendation && (
            <div className="about-row">
              <strong>Agent trace</strong>
              <p>{agentRecommendation.trace.nodes.join(" -> ")}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
