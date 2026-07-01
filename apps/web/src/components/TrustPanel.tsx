"use client";

import { useState } from "react";

import type {
  AllergyTag,
  AskRestaurantResponse,
  MenuItem,
  MenuRefreshJob,
  PlaceDetailsResponse,
  PlaceDetailState,
  PlaceSummary,
} from "@/lib/types";

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
type VerificationTone = "needs-check" | "possible" | "possible-weak" | "avoid" | "unknown";

interface MenuVerification {
  label: "Needs check" | "Possible lower-risk" | "Avoid" | "Insufficient info";
  tone: VerificationTone;
  metadata: string;
  detail: string;
}

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

function formatAllergen(value: AllergyTag): string {
  return value.replace(/_/g, " ");
}

function getMenuVerification(
  item: MenuItem,
  selectedAllergens: AllergyTag[],
  fallbackConfidence?: number | null,
): MenuVerification {
  const detectedAllergens = Array.from(
    new Set(
      [...(item.matched_allergens ?? []), ...item.likely_risky_for].filter((allergen) =>
        selectedAllergens.includes(allergen),
      ),
    ),
  );
  const confidence = item.confidence ?? item.ocr_confidence ?? fallbackConfidence;
  const confidenceDetail = typeof confidence === "number" ? `${Math.round(confidence * 100)}% evidence confidence.` : null;
  const detail = [item.risk_reasons?.join(" "), item.verification_question, confidenceDetail].filter(Boolean).join(" ");

  if (item.risk_label === "avoid" || detectedAllergens.length > 0) {
    const allergenList = detectedAllergens.map(formatAllergen).join(", ");
    return {
      label: "Avoid",
      tone: "avoid",
      metadata: allergenList ? `${allergenList} detected` : "selected allergen detected",
      detail: detail || `Selected allergen evidence was detected: ${allergenList}.`,
    };
  }

  if (item.risk_label === "needs_check") {
    return {
      label: "Needs check",
      tone: "needs-check",
      metadata: "preparation needs staff review",
      detail: detail || "Preparation or ingredient wording needs staff verification.",
    };
  }

  if (item.risk_label === "insufficient_info" || !item.description?.trim()) {
    return {
      label: "Insufficient info",
      tone: "unknown",
      metadata: "ingredient details missing",
      detail: detail || "The menu source does not provide enough ingredient or preparation detail.",
    };
  }

  return {
    label: "Possible lower-risk",
    tone: typeof confidence === "number" && confidence < 0.72 ? "possible-weak" : "possible",
    metadata: "no selected allergen detected · verify prep",
    detail: detail || "No selected allergen was detected in the available menu text. Verify preparation with staff.",
  };
}

function traceStatusLabel(status: string): string {
  return status === "fallback_local" ? "complete" : status.replaceAll("_", " ");
}

function traceDetail(step: MenuRefreshJob["trace"][number]): string {
  if (step.status === "fallback_local" || step.detail.toLowerCase().includes("continued with local ingestion")) {
    return "Cloud job could not be saved, so this scan ran directly.";
  }
  return step.detail;
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
  const allergyMode = data.selected_allergens.length > 0;
  const classifiedMenuItems = menuSections.flatMap((section) =>
    section.items.map((item) => ({
      item,
      sectionTitle: section.title,
      verification: getMenuVerification(item, data.selected_allergens, data.menu?.extraction_confidence),
    })),
  );
  const possibleMenuItems = classifiedMenuItems
    .filter((entry) => entry.verification.label === "Possible lower-risk")
    .sort((left, right) => (right.item.confidence ?? 0) - (left.item.confidence ?? 0));
  const needsCheckMenuItems = classifiedMenuItems.filter((entry) => entry.verification.label === "Needs check");
  const avoidMenuItems = classifiedMenuItems.filter((entry) => entry.verification.label === "Avoid");
  const insufficientMenuItems = classifiedMenuItems.filter((entry) => entry.verification.label === "Insufficient info");
  const menuRiskGroups = [
    {
      key: "possible",
      title: "Possible lower-risk items to ask about",
      tone: "possible",
      count: possibleMenuItems.length,
      items: possibleMenuItems.slice(0, 5),
    },
    {
      key: "check",
      title: "Needs staff check",
      tone: "needs-check",
      count: needsCheckMenuItems.length,
      items: needsCheckMenuItems.slice(0, 6),
    },
    {
      key: "avoid",
      title: "Avoid for your allergies",
      tone: "avoid",
      count: avoidMenuItems.length,
      items: avoidMenuItems.slice(0, 6),
    },
    {
      key: "insufficient",
      title: "Insufficient info",
      tone: "unknown",
      count: insufficientMenuItems.length,
      items: insufficientMenuItems.slice(0, 6),
    },
  ];
  const menuBucketCounts = {
    possible: data.menu?.possible_lower_risk_count ?? possibleMenuItems.length,
    check: data.menu?.needs_check_count ?? needsCheckMenuItems.length,
    avoid: data.menu?.avoid_count ?? avoidMenuItems.length,
    insufficient: data.menu?.insufficient_info_count ?? insufficientMenuItems.length,
  };
  const restaurantFitScore = data.restaurant_fit_score ?? data.menu?.restaurant_fit_score ?? 20;
  const restaurantFitLabel =
    data.restaurant_fit_label ?? data.menu?.restaurant_fit_label ?? (menuItemCount > 0 ? "Needs verification" : "Scan needed");
  const hasRestaurantFit = allergyMode && menuItemCount > 0 && restaurantFitScore != null;
  const restaurantFitTone = restaurantFitScore >= 70 ? "good" : restaurantFitScore >= 45 ? "caution" : "risk";
  const restaurantFitMessage =
    menuBucketCounts.avoid > 0 && menuBucketCounts.possible > 0
      ? "Some dishes contain your allergens, but many menu items may be possible lower-risk after staff verification."
      : menuBucketCounts.possible > 0
        ? "Several menu items may be possible lower-risk after staff verification."
        : "The current menu evidence still needs careful staff verification.";
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
  const indexingStatus =
    menuRefreshJob?.indexing_status ??
    menuRefreshJob?.trace.find((step) => step.id === "search_index")?.status ??
    null;
  const scanHasRun = Boolean(menuRefreshJob);
  const ragStatus =
    indexingStatus === "complete"
      ? { className: "rag-ready", label: "RAG index ready" }
      : indexingStatus === "pending" || indexingStatus === "running"
        ? { className: "rag-updating", label: "RAG index updating" }
        : indexingStatus === "failed"
          ? { className: "rag-unavailable", label: "RAG index unavailable" }
          : menuItemCount > 0
            ? { className: "rag-ready", label: "RAG index ready" }
            : scanHasRun
              ? { className: "rag-updating", label: "RAG index updating" }
              : null;
  const refreshFailed = menuRefreshJob?.status === "failed";
  const refreshPending =
    isMenuLoading ||
    ["queued", "running", "discovering", "ocr_processing", "normalizing", "indexing", "needs_background_refresh"].includes(
      menuRefreshJob?.status ?? "",
    );
  const menuLifecycleLabel =
    menuItemCount > 0 && indexingStatus === "complete"
      ? "Menu found · RAG index ready"
      : menuItemCount > 0 && refreshPending
        ? "Menu found · deeper scan running"
        : menuItemCount > 0
          ? "Menu found"
          : refreshPending
            ? "Menu scan running"
            : "No menu evidence";
  const ocrTrace = menuRefreshJob?.trace.find((step) => step.id === "document_ocr");
  const ocrStatus =
    data.menu?.extraction_method?.includes("azure_document_intelligence") || ocrTrace?.status === "complete"
      ? { className: "ocr-used", label: "OCR used" }
      : ocrTrace?.status === "running"
        ? { className: "ocr-checking", label: "OCR checking" }
        : scanHasRun || menuItemCount > 0
          ? { className: "ocr-skipped", label: "OCR skipped" }
          : null;
  const ratingLine = [
    data.rating ? `${data.rating.toFixed(1)} on Google` : null,
    data.user_rating_count ? `${data.user_rating_count.toLocaleString()} reviews` : null,
    data.price_range ?? data.price_level?.replace("PRICE_LEVEL_", "").replace(/_/g, " ").toLowerCase() ?? null,
    formatPlaceType(data.primary_type),
  ].filter(Boolean).join(" · ");
  const generalMatchLabel = (data.rating ?? 0) >= 4.5 ? "Popular nearby option" : "Restaurant match";

  return (
    <div className="trust-panel-content">
      <div className="place-sheet-header">
        <p className="panel-eyebrow">Place details</p>
        <div className="place-title-with-fit">
          <h2>{data.name}</h2>
          {hasRestaurantFit && <span className={`restaurant-fit-badge ${restaurantFitTone}`}>{restaurantFitScore}</span>}
          {!allergyMode && data.rating != null && <span className="restaurant-rating-badge">{data.rating.toFixed(1)}★</span>}
        </div>
        {hasRestaurantFit && <p className="restaurant-fit-label">{restaurantFitLabel}</p>}
        {!allergyMode && <p className="restaurant-fit-label">{generalMatchLabel}</p>}
        <p>{data.address ?? "Address unavailable"}</p>
        {ratingLine && <p>{ratingLine}</p>}
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
          {allergyMode && !hasRestaurantFit && (
            <div className="overview-line">
              <strong>Allergy read</strong>
              <p>{data.decision_brief.summary}</p>
            </div>
          )}
          {hasRestaurantFit && (
            <div className={`overview-line restaurant-fit-overview ${restaurantFitTone}`}>
              <strong>{restaurantFitLabel}</strong>
              <p>{restaurantFitMessage}</p>
            </div>
          )}
          {allergyMode && agentRecommendation && !hasRestaurantFit && (
            <div className={`overview-line agent-risk ${agentRecommendation.overall_risk}`}>
              <strong>
                Agentic risk: {formatRiskLabel(agentRecommendation.overall_risk)} ·{" "}
                {formatRiskLabel(agentRecommendation.recommended_action)}
              </strong>
              <p>{agentRecommendation.summary}</p>
              {agentConfidencePercent !== null && <p>{agentConfidencePercent}% source confidence.</p>}
            </div>
          )}
          {allergyMode && agentRecommendation && agentRecommendation.missing_information.length > 0 && (
            <div className="overview-line">
              <strong>Missing information</strong>
              <p>{agentRecommendation.missing_information.slice(0, 2).join(" ")}</p>
            </div>
          )}
          {allergyMode && agentRecommendation && agentRecommendation.recommended_questions.length > 0 && (
            <div className="overview-line">
              <strong>Questions for staff</strong>
              <p>{agentRecommendation.recommended_questions.slice(0, 2).join(" ")}</p>
            </div>
          )}
        </div>
      )}

      {activeTab === "menu" && (
        <div className="place-tab-panel">
          <div
            className="place-status-row menu-tab-status-row"
            title={allergyMode ? `Source confidence ${confidencePercent}%. Evidence fit ${data.score_summary.fit_score}/100.` : "Menu extraction status"}
            aria-label="Menu and retrieval status"
          >
            <span className={menuItemCount > 0 ? "menu-found" : "menu-pending"}>
              {menuLifecycleLabel}
            </span>
            {allergyMode && <span className="needs-verification">{restaurantFitLabel}</span>}
            {ragStatus && !menuLifecycleLabel.includes("RAG index ready") && <span className={ragStatus.className}>{ragStatus.label}</span>}
            {ocrStatus && <span className={ocrStatus.className}>{ocrStatus.label}</span>}
            {refreshFailed && menuItemCount > 0 && <span className="refresh-failed">Refresh failed</span>}
          </div>
          {hasRestaurantFit && (
            <div className="menu-fit-summary" aria-label="Restaurant allergy fit summary">
              <strong>
                Restaurant allergy fit: {restaurantFitScore} · {restaurantFitLabel}
              </strong>
              <p>
                {menuBucketCounts.possible} possible lower-risk · {menuBucketCounts.check} needs check · {menuBucketCounts.avoid} avoid · {menuBucketCounts.insufficient} insufficient info
              </p>
            </div>
          )}
          <div className="menu-source-row">
            <div>
              <strong>Menu</strong>
              <p>
                {menuItemCount > 0
                  ? allergyMode
                    ? `${menuItemCount} dish-level item${menuItemCount === 1 ? "" : "s"} extracted from available menu evidence. Verify ingredients and prep with staff.`
                    : `${menuItemCount} menu item${menuItemCount === 1 ? "" : "s"} found.`
                  : refreshPending
                    ? "Menu scan is still running."
                  : scanHasRun
                    ? "No stored menu evidence yet."
                    : "No menu scanned yet."}
              </p>
              {menuEvidenceLine && <p className="muted-line">{menuEvidenceLine}</p>}
              {refreshFailed && menuItemCount > 0 && (
                <p className="menu-refresh-warning">Latest saved menu shown; refresh failed.</p>
              )}
              {refreshPending && menuItemCount > 0 && (
                <p className="muted-line">Latest saved menu shown while the refresh continues.</p>
              )}
            </div>
            <div className="menu-source-actions">
              {(data.menu?.source_url || data.menu?.document_url) && (
                <a className="source-link" href={data.menu.source_url ?? data.menu.document_url ?? ""} target="_blank" rel="noreferrer">
                  Source
                </a>
              )}
              {menuItemCount > 0 && (
                <button type="button" className="retry-button" onClick={onRefreshMenu} disabled={refreshPending}>
                  Refresh menu
                </button>
              )}
            </div>
          </div>
          {refreshPending && menuSections.length === 0 ? (
            <div className="menu-loading-state">
              <strong>Menu scan is still running</strong>
              <p>Extracted items will appear here as soon as the scan finishes.</p>
              <div className="skeleton skeleton-line" />
              <div className="skeleton skeleton-line" />
              <div className="skeleton skeleton-review" />
            </div>
          ) : menuSections.length > 0 && allergyMode ? (
            <div className="menu-risk-groups">
              {menuRiskGroups.filter((group) => group.items.length > 0).map((group) => (
                <section key={group.key} className={`menu-risk-group ${group.tone}`}>
                  <div className="menu-risk-group-header">
                    <h3>{group.title}</h3>
                    <span>{group.count}</span>
                  </div>
                  {group.items.map(({ item, sectionTitle, verification }) => {
                    const tooltip = [item.description, verification.detail].filter(Boolean).join(" ");
                    return (
                      <article
                        key={`${sectionTitle}-${item.name}`}
                        className="menu-list-item compact-menu-row"
                        title={tooltip}
                      >
                        <div>
                          <div className="menu-item-heading">
                            <strong>{item.name}</strong>
                            <span
                              className={`menu-status-chip ${verification.tone}`}
                              title={verification.detail}
                            >
                              {verification.label}
                            </span>
                          </div>
                          <p className={`menu-item-meta ${verification.tone}`}>
                            {sectionTitle} · {verification.metadata}
                          </p>
                        </div>
                        {item.price && <span className="menu-price">{item.price}</span>}
                      </article>
                    );
                  })}
                </section>
              ))}
            </div>
          ) : menuSections.length > 0 ? (
            <div className="menu-risk-groups general-menu-groups">
              {menuSections.map((section) => (
                <section key={section.title} className="menu-risk-group general">
                  <div className="menu-risk-group-header">
                    <h3>{section.title}</h3>
                    <span>{section.items.length}</span>
                  </div>
                  {section.items.slice(0, 12).map((item) => (
                    <article key={`${section.title}-${item.name}`} className="menu-list-item compact-menu-row">
                      <div>
                        <div className="menu-item-heading">
                          <strong>{item.name}</strong>
                        </div>
                        {item.description && <p className="menu-item-meta">{item.description}</p>}
                      </div>
                      {item.price && <span className="menu-price">{item.price}</span>}
                    </article>
                  ))}
                </section>
              ))}
            </div>
          ) : !scanHasRun ? (
            <article className="empty-menu-state">
              <strong>No menu scanned yet</strong>
              <p>Start a scan to check the official website and any linked PDF or image menus.</p>
              <button type="button" className="retry-button" onClick={onRefreshMenu}>
                Scan menu
              </button>
            </article>
          ) : (
            <article className="empty-menu-state">
              <strong>No stored menu evidence yet</strong>
              <p>Try the menu scan again or open the restaurant website to verify current menu information.</p>
              {data.website_uri && (
                <a className="source-link" href={data.website_uri} target="_blank" rel="noreferrer">
                  Restaurant website
                </a>
              )}
              <button type="button" className="retry-button" onClick={onRefreshMenu}>
                Retry menu scan
              </button>
            </article>
          )}

          {(isMenuLoading || menuRefreshJob) && (
            <details className="menu-trace">
              <summary>
                <strong>Technical trace</strong>
                <span className={`trace-status ${isMenuLoading ? "running" : indexingStatus ?? menuRefreshJob?.status ?? "idle"}`}>
                  {refreshPending
                    ? "Running"
                    : refreshFailed
                      ? "Needs attention"
                      : indexingStatus === "complete" || menuRefreshJob?.status === "complete"
                        ? "Complete"
                        : "Available"}
                </span>
              </summary>
              <div className="menu-trace-list">
                {(menuRefreshJob?.total_documents ?? 0) > 0 && (
                  <p className="muted-line">
                    {menuRefreshJob?.processed_documents ?? 0} of {menuRefreshJob?.total_documents ?? 0} menu pages processed
                    {menuRefreshJob?.menu_version ? ` · ${menuRefreshJob.menu_version}` : ""}
                  </p>
                )}
                {(menuRefreshJob?.trace ?? []).map((step) => (
                  <article key={step.id} className={`menu-trace-step ${step.status}`}>
                    <div>
                      <strong>{step.label}</strong>
                      <span>{traceStatusLabel(step.status)}</span>
                    </div>
                    <p>{traceDetail(step)}</p>
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
              {!isMenuLoading &&
                (menuRefreshJob?.status === "failed" || menuRefreshJob?.status === "needs_background_refresh") && (
                <button type="button" className="retry-button" onClick={onRefreshMenu}>
                  Retry menu scan
                </button>
              )}
            </details>
          )}

          {allergyMode && (
            <button type="button" className="ask-button" onClick={onAskRestaurant} disabled={isAskingRestaurant}>
              {isAskingRestaurant ? "Saving question..." : "Ask restaurant to verify"}
            </button>
          )}
          {allergyMode && askResponse && <p className="menu-job-note">{askResponse.suggested_script}</p>}
        </div>
      )}

      {activeTab === "reviews" && (
        <div className="place-tab-panel">
          {allergyMode && <p className="panel-note">{signalSource}</p>}
          <p className="panel-note">{reviewSourceLine}</p>

          {allergyMode && <div className="review-group">
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
          </div>}

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
            <strong>Verification note</strong>
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
