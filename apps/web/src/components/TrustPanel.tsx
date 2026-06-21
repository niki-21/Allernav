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

export default function TrustPanel({
  place,
  detailState,
  onRetry,
  onAskRestaurant,
  askResponse,
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
  const reviewSource = data.review_source_summary;
  const reviewSignalCount = data.evidence.length;
  const signalSource =
    reviewSignalCount > 0 && menuItemCount > 0
      ? `${reviewSignalCount} allergy signal${reviewSignalCount === 1 ? "" : "s"} + ${menuItemCount} menu item${menuItemCount === 1 ? "" : "s"}`
      : reviewSignalCount > 0
        ? `${reviewSignalCount} allergy signal${reviewSignalCount === 1 ? "" : "s"}`
        : menuItemCount > 0
          ? `${menuItemCount} menu item${menuItemCount === 1 ? "" : "s"}`
          : "Very limited signal";
  const reviewSourceLine = reviewSource
    ? reviewSource.expanded_reviews_configured
      ? reviewSource.expanded_review_count > 0
        ? `Apify expanded reviews analyzed: ${reviewSource.expanded_review_count}. Showing ${reviewSource.displayed_review_count} most relevant of ${reviewSource.analyzed_review_count} total review snippets.`
        : `Apify is configured, but no expanded reviews were returned for this place. Showing ${reviewSource.google_review_count} Google snippet${reviewSource.google_review_count === 1 ? "" : "s"}.`
      : `Apify is not configured for this running server. Showing Google’s limited review sample of ${reviewSource.google_review_count} snippet${reviewSource.google_review_count === 1 ? "" : "s"}.`
    : "Showing the review snippets returned by the current place details source.";
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
          Allergy fit {data.score_summary.fit_score} · {confidencePercent}% confidence · verify before ordering
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
          {data.recommended_items.length > 0 && (
            <div className="verify-list">
              <strong>Items to verify</strong>
              {data.recommended_items.slice(0, 5).map((item) => (
                <article
                  key={`${item.section_title ?? "pick"}-${item.name}`}
                  className="verify-item-row"
                  title={`${item.reason}${item.caution ? ` ${item.caution}` : ""}`}
                >
                  <div>
                    <strong>{item.name}</strong>
                    <p>{item.reason}</p>
                    {item.caution && <p className="muted-line">{item.caution}</p>}
                  </div>
                  <span>Verify</span>
                </article>
              ))}
            </div>
          )}

          {menuSections.length > 0 ? (
            <div className="menu-section-list google-menu-list">
              {menuSections.slice(0, 3).map((section) => (
                <section key={section.title} className="menu-list-section">
                  <h3>{section.title}</h3>
                  {section.items.slice(0, 6).map((item) => (
                    <article
                      key={`${section.title}-${item.name}`}
                      className="menu-list-item compact-menu-row"
                      title={item.description ?? "Menu item extracted from source. Verify ingredients with staff."}
                    >
                      <div>
                        <strong>{item.name}</strong>
                        {item.description && <p>{item.description}</p>}
                        {item.likely_risky_for.some((allergen) => data.selected_allergens.includes(allergen)) && (
                          <p className="menu-risk-note">
                            Watch:{" "}
                            {item.likely_risky_for
                              .filter((allergen) => data.selected_allergens.includes(allergen))
                              .map((allergen) => allergen.replace("_", " "))
                              .join(", ")}
                          </p>
                        )}
                      </div>
                      <span>{item.price ?? "Verify"}</span>
                    </article>
                  ))}
                </section>
              ))}
            </div>
          ) : (
            <article className="empty-menu-state">
              <strong>No dish-level menu captured</strong>
              <p>
                Official menu pages, PDFs, and accessible menu images are checked when available. If extraction is too
                weak or only returns hours/events, AllerNav keeps this as insufficient evidence.
              </p>
              {data.website_uri && (
                <a className="source-link" href={data.website_uri} target="_blank" rel="noreferrer">
                  Restaurant website
                </a>
              )}
            </article>
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
          <p className="panel-note">{reviewSourceLine}</p>

          <div className="review-group">
            <strong>Allergy review signals</strong>
            <p className="panel-note">
              Reviews are warning context only. AllerNav does not use them to prove that a dish is lower risk.
            </p>
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

          {data.evidence.length === 0 && reviewSnippets.length > 0 && (
            <div className="review-group">
              <strong>Returned review sample</strong>
              <p className="panel-note">
                These snippets were returned, but no allergy-specific terms matched your selected allergens.
              </p>
              <div className="evidence-list compact">
                {reviewSnippets.slice(0, 3).map((review) => (
                  <article key={review.review_id} className="evidence-item neutral">
                    <div className="evidence-item-header">
                      <span>{review.author_name ?? "Review"}</span>
                      <span>{review.rating ? `${review.rating.toFixed(1)}★` : review.relative_publish_time ?? "Review"}</span>
                    </div>
                    <p className="evidence-excerpt">{review.text}</p>
                  </article>
                ))}
              </div>
            </div>
          )}
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
