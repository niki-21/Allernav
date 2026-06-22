export type AllergyTag =
  | "peanut"
  | "tree_nut"
  | "dairy"
  | "egg"
  | "shellfish"
  | "fish"
  | "soy"
  | "sesame"
  | "wheat_gluten";

export type ProfileSensitivity = "watchful" | "careful" | "strict";
export type DiningMode = "grab_go" | "sit_down" | "late_night" | "study_break";
export type Verdict = "good_fit" | "use_caution" | "high_risk";
export type ImpactDirection = "positive" | "negative";
export type EvidenceStatus = "meaningful" | "limited";
export type EvidenceTone = "reassuring" | "risk_note";
export type AgentRiskLevel = "low" | "medium" | "high" | "insufficient_evidence";
export type AgentRecommendedAction = "verify" | "avoid" | "ask_staff" | "insufficient_evidence";
export type AgentSourceType = "official_menu" | "restaurant_website" | "review" | "fixture" | "user_upload" | "unknown";
export type SignalType =
  | "accommodation"
  | "staff_knowledge"
  | "menu_labeling"
  | "cross_contact_risk"
  | "reaction_report"
  | "uncertainty";

export interface LatLng {
  lat: number;
  lng: number;
}

export interface PlaceSummary {
  id: string;
  name: string;
  address?: string | null;
  location: LatLng;
  rating?: number | null;
  user_rating_count?: number | null;
  primary_type?: string | null;
}

export interface PlaceScoreSummary {
  score: number;
  verdict: Verdict;
  confidence: number;
  fit_score: number;
  fit_verdict: Verdict;
  evidence_confidence: number;
  positive_signals: string[];
  negative_signals: string[];
  evidence_count: number;
  meaningful_evidence: boolean;
  evidence_status: EvidenceStatus;
  evidence_summary: string;
}

export interface ReviewEvidence {
  review_id: string;
  author_name?: string | null;
  rating?: number | null;
  text: string;
  matched_allergens: AllergyTag[];
  signal_type: SignalType;
  impact: ImpactDirection;
  excerpt: string;
  matched_phrase: string;
  signal_label: string;
  tone: EvidenceTone;
  is_allergy_relevant: boolean;
  weight: number;
  publish_time?: string | null;
}

export interface PlaceReviewSnippet {
  review_id: string;
  author_name?: string | null;
  rating?: number | null;
  text: string;
  publish_time?: string | null;
  relative_publish_time?: string | null;
}

export interface ReviewSourceSummary {
  google_review_count: number;
  expanded_review_count: number;
  local_snapshot_review_count: number;
  analyzed_review_count: number;
  displayed_review_count: number;
  expanded_reviews_configured: boolean;
  expanded_review_provider?: "apify" | null;
  expanded_review_status?: "not_configured" | "deferred" | "loaded" | "failed";
}

export interface PlacePhoto {
  name: string;
  url: string;
  width_px?: number | null;
  height_px?: number | null;
  author_names: string[];
}

export interface PlaceOpeningHours {
  openNow?: boolean | null;
  weekdayDescriptions?: string[];
}

export interface MenuItem {
  name: string;
  description?: string | null;
  price?: string | null;
  likely_safe_for: AllergyTag[];
  likely_risky_for: AllergyTag[];
}

export interface MenuSection {
  title: string;
  items: MenuItem[];
}

export interface PlaceMenu {
  source_url?: string | null;
  sections: MenuSection[];
}

export interface RecommendedMenuItem {
  name: string;
  section_title?: string | null;
  reason: string;
  caution?: string | null;
  source: "heuristic" | "llm";
}

export interface MenuRefreshJob {
  id: string;
  place_id: string;
  status: "queued" | "running" | "complete" | "failed";
  message: string;
  created_at: string;
  completed_at?: string | null;
}

export interface ReviewRefreshJob {
  id: string;
  place_id: string;
  status: "queued" | "running" | "complete" | "failed" | "skipped";
  message: string;
  reviews_count: number;
  reviews?: PlaceReviewSnippet[];
  created_at: string;
  completed_at?: string | null;
}

export interface AskRestaurantResponse {
  id: string;
  status: "queued" | "sent" | "failed";
  message: string;
  suggested_script: string;
}

export interface PlaceDecisionBrief {
  headline: string;
  summary: string;
  recommended_action: string;
  caution_flags: string[];
}

export interface PlatformUserProfile {
  id: string;
  name: string;
  email?: string | null;
  auth_provider: "google";
}

export interface CommunityReview {
  id: string;
  author_name: string;
  body: string;
  created_at: string;
  verification_status: "verified_visit" | "signed_in" | "unverified";
}

export interface AgentEvidenceFragment {
  id: string;
  source_type: AgentSourceType;
  text: string;
  source_url?: string | null;
  source_timestamp?: string | null;
  dish_name?: string | null;
  matched_allergens: AllergyTag[];
  reliability: number;
}

export interface DishRiskResult {
  dish: string;
  risk_level: AgentRiskLevel;
  confidence: number;
  detected_allergens: AllergyTag[];
  evidence: AgentEvidenceFragment[];
  missing_information: string[];
  recommended_questions: string[];
  recommended_action: AgentRecommendedAction;
}

export interface AgentTraceSummary {
  nodes: string[];
  tool_calls: string[];
  abstained: boolean;
  routed_to_safety_gate: boolean;
}

export interface AgentRecommendationResult {
  restaurant_id?: string | null;
  restaurant_name?: string | null;
  overall_risk: AgentRiskLevel;
  confidence: number;
  summary: string;
  dish_results: DishRiskResult[];
  evidence: AgentEvidenceFragment[];
  missing_information: string[];
  recommended_questions: string[];
  recommended_action: AgentRecommendedAction;
  trace: AgentTraceSummary;
}

export interface PlaceDetailsResponse extends PlaceSummary {
  website_uri?: string | null;
  editorial_summary?: string | null;
  national_phone_number?: string | null;
  international_phone_number?: string | null;
  price_level?: string | null;
  price_range?: string | null;
  regular_opening_hours?: PlaceOpeningHours | null;
  current_opening_hours?: PlaceOpeningHours | null;
  service_options?: Record<string, boolean | null | undefined>;
  google_maps_uri: string;
  google_review_uri: string;
  selected_allergens: AllergyTag[];
  score_summary: PlaceScoreSummary;
  evidence: ReviewEvidence[];
  review_snippets: PlaceReviewSnippet[];
  review_source_summary?: ReviewSourceSummary;
  photos: PlacePhoto[];
  explanation: string;
  decision_brief: PlaceDecisionBrief;
  menu: PlaceMenu | null;
  recommended_items: RecommendedMenuItem[];
  community_reviews: CommunityReview[];
  agent_recommendation?: AgentRecommendationResult | null;
}

export interface SearchResponse {
  query: string;
  center: LatLng;
  allergens: AllergyTag[];
  places: PlaceSummary[];
}

export type PlaceDetailState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; data: PlaceDetailsResponse }
  | { status: "error"; message: string };
