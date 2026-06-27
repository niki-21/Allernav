"use client";

import { useState } from "react";

import type { AskRestaurantResponse, MenuRefreshJob, PlaceDetailsResponse, PlaceDetailState, PlaceSummary } from "@/lib/types";

interface TrustPanelProps {
  place: PlaceSummary | null;
  detailState: PlaceDetailState | undefined;
  onRetry: () => void;
  onAskRestaurant: () => void;
  askResponse?: AskRestaurantResponse | null;
  isAskingRestaurant?: boolean;
  isMenuLoading?: boolean;
  menuRefreshJob?: MenuRefreshJob;
  onRefreshMenu: () => void;
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

function formatExtractionMethod(value?: string | null): string | null {
  if (!value) {
    return null;
  }
  if (value.includes("azure_document_intelligence")) {
    return "Azure Document Intelligence OCR";
  }
  return value.replace(/_/g, " ");
}

export default function TrustPanel({
  place,
  detailState,
  onRetry,
  onAskRestaurant,
  askResponse,
  isAskingRestaurant = false,
  isMenuLoading = false,
  menuRefreshJob,
  onRefreshMenu,
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
  const reviewSourceLine = reviewSource
    ? reviewSource.expanded_reviews_configured
      ? reviewSource.expanded_review_status === "deferred"
        ? `Expanded Apify reviews are configured but loaded separately so place details stay fast. Showing ${reviewSource.google_review_count} Google snippet${reviewSource.google_review_count === 1 ? "" : "s"} now.`
        : reviewSource.expanded_review_count > 0
        ? `Apify expanded reviews analyzed: ${reviewSource.expanded_review_count}. Showing ${reviewSource.displayed_review_count} most relevant of ${reviewSource.analyzed_review_count} total review snippets.`
        : `Apify is configured, but no expanded reviews were returned for this place. Showing ${reviewSource.google_review_count} Google snippet${reviewSource.google_review_count === 1 ? "" : "s"}.`
      : `Apify is not configured for this running server. Showing Google’s limited review sample of ${reviewSource.google_review_count} snippet${reviewSource.google_review_count === 1 ? "" : "s"}.`
    : "Showing the review snippets returned by the current place details source.";
  const confidencePercent = Math.round(data.score_summary.evidence_confidence * 100);
  const agentRecommendation = data.agent_recommendation ?? null;
  const agentDishResults = agentRecommendation?.dish_results ?? [];
  const hasAgentDishEvidence = agentDishResults.length > 0;
  const agentConfidencePercent = agentRecommendation ? Math.round(agentRecommendation.confidence * 100) : null;
  const openStatus = formatOpenStatus(data);
  const services = serviceLabels(data.service_options);
  const extractionMethod = formatExtractionMethod(data.menu?.extraction_method);
  const extractionConfidence =
    typeof data.menu?.extraction_confidence === "number"
      ? `${Math.round(data.menu.extraction_confidence * 100)}% extraction confidence`
      : null;
  const menuEvidenceLine = [extractionMethod, extractionConfidence, data.menu?.page_count ? `${data.menu.page_count} page${data.menu.page_count === 1 ? "" : "s"}` : null]
    .filter(Boolean)
    .join(" · ");
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
                  ? `${menuItemCount} dish-level item${menuItemCount === 1 ? "" : "s"} extracted from available menu evidence. Verify ingredients and prep with staff.`
                  : hasAgentDishEvidence
                  ? `${agentDishResults.length} agent dish result${agentDishResults.length === 1 ? "" : "s"} found, but the structured menu view is still being normalized.`
                  : "No reliable dish-level menu found yet."}
              </p>
              {menuEvidenceLine && <p className="muted-line">{menuEvidenceLine}</p>}
            </div>
            {(data.menu?.source_url || data.menu?.document_url) && (
              <a className="source-link" href={data.menu.source_url ?? data.menu.document_url ?? ""} target="_blank" rel="noreferrer">
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

          {isMenuLoading && menuSections.length === 0 ? (
            <div className="menu-loading-state">
              <strong>Loading menu evidence</strong>
              <p>AllerNav is checking the restaurant website and linked menu documents.</p>
              <div className="skeleton skeleton-line" />
              <div className="skeleton skeleton-line" />
              <div className="skeleton skeleton-review" />
            </div>
          ) : menuSections.length > 0 ? (
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
          ) : hasAgentDishEvidence ? (
            <article className="empty-menu-state">
              <strong>Dish evidence found by agent analysis</strong>
              <p>
                The structured menu panel is not populated yet, but AllerNav found dish-level evidence through the
                agentic safety check. Treat these as verification targets, not confirmed lower-risk dishes.
              </p>
              {data.website_uri && (
                <a className="source-link" href={data.website_uri} target="_blank" rel="noreferrer">
                  Restaurant website
                </a>
              )}
            </article>
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

          {(isMenuLoading || menuRefreshJob) && (
            <details className="menu-trace" open={isMenuLoading || menuRefreshJob?.status === "failed"}>
              <summary>
                <strong>Menu agent trace</strong>
                <span className={`trace-status ${isMenuLoading ? "running" : menuRefreshJob?.status ?? "idle"}`}>
                  {isMenuLoading ? "Running" : menuRefreshJob?.status ?? "Idle"}
                </span>
              </summary>
              <div className="menu-trace-list">
                {(menuRefreshJob?.trace ?? []).map((step) => (
                  <article key={step.id} className={`menu-trace-step ${step.status}`}>
                    <div>
                      <strong>{step.label}</strong>
                      <span>{step.status}</span>
                    </div>
                    <p>{step.detail}</p>
                    <small>
                      {[step.provider?.replaceAll("_", " "), typeof step.duration_ms === "number" ? `${step.duration_ms} ms` : null]
                        .filter(Boolean)
                        .join(" · ")}
                    </small>
                    {step.source_url && (
                      <a href={step.source_url} target="_blank" rel="noreferrer">
                        Inspect source
                      </a>
                    )}
                  </article>
                ))}
              </div>
              {!isMenuLoading && menuRefreshJob?.status === "failed" && (
                <button type="button" className="retry-button" onClick={onRefreshMenu}>
                  Retry menu scan
                </button>
              )}
            </details>
          )}

          {agentRecommendation && hasAgentDishEvidence && (
            <div className="menu-section-list compact-recommendations">
              <strong>Agent dish evidence</strong>
              {agentDishResults.slice(0, 3).map((item) => (
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
