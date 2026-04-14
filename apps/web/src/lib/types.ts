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

export type Verdict = "good_fit" | "use_caution" | "high_risk";
export type ImpactDirection = "positive" | "negative";
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
  positive_signals: string[];
  negative_signals: string[];
  evidence_count: number;
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
  weight: number;
  publish_time?: string | null;
}

export interface PlaceDetailsResponse extends PlaceSummary {
  website_uri?: string | null;
  editorial_summary?: string | null;
  selected_allergens: AllergyTag[];
  score_summary: PlaceScoreSummary;
  evidence: ReviewEvidence[];
  explanation: string;
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

