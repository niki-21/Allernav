from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class AllergyTag(str, Enum):
    PEANUT = "peanut"
    TREE_NUT = "tree_nut"
    DAIRY = "dairy"
    EGG = "egg"
    SHELLFISH = "shellfish"
    FISH = "fish"
    SOY = "soy"
    SESAME = "sesame"
    WHEAT_GLUTEN = "wheat_gluten"


class Verdict(str, Enum):
    GOOD_FIT = "good_fit"
    USE_CAUTION = "use_caution"
    HIGH_RISK = "high_risk"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class RecommendedAction(str, Enum):
    VERIFY = "verify"
    AVOID = "avoid"
    ASK_STAFF = "ask_staff"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class SourceType(str, Enum):
    OFFICIAL_MENU = "official_menu"
    RESTAURANT_WEBSITE = "restaurant_website"
    REVIEW = "review"
    FIXTURE = "fixture"
    USER_UPLOAD = "user_upload"
    UNKNOWN = "unknown"


class SignalType(str, Enum):
    ACCOMMODATION = "accommodation"
    STAFF_KNOWLEDGE = "staff_knowledge"
    MENU_LABELING = "menu_labeling"
    CROSS_CONTACT_RISK = "cross_contact_risk"
    REACTION_REPORT = "reaction_report"
    UNCERTAINTY = "uncertainty"


class ImpactDirection(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class LatLng(BaseModel):
    lat: float
    lng: float


class AllergyProfile(BaseModel):
    allergens: list[AllergyTag] = Field(default_factory=list)
    sensitivity: str = "careful"
    prep_preference: str = "verify"


class SearchRequest(BaseModel):
    query: str = ""
    center: LatLng | None = None
    allergens: list[AllergyTag] = Field(default_factory=list)
    max_results: int = Field(default=12, ge=1, le=20)


class PlaceListItem(BaseModel):
    id: str
    name: str
    address: str | None = None
    location: LatLng
    rating: float | None = None
    user_rating_count: int | None = None
    primary_type: str | None = None


class SearchResponse(BaseModel):
    query: str
    center: LatLng
    allergens: list[AllergyTag]
    places: list[PlaceListItem]


class PlaceScoreSummary(BaseModel):
    score: int = Field(ge=0, le=100)
    verdict: Verdict
    confidence: float = Field(ge=0, le=1)
    fit_score: int = Field(default=0, ge=0, le=100)
    fit_verdict: Verdict | None = None
    evidence_confidence: float = Field(default=0, ge=0, le=1)
    positive_signals: list[str] = Field(default_factory=list)
    negative_signals: list[str] = Field(default_factory=list)
    evidence_count: int = Field(default=0, ge=0)
    meaningful_evidence: bool = False
    evidence_status: str = "limited"
    evidence_summary: str = "Limited allergy evidence"


class ReviewEvidence(BaseModel):
    review_id: str
    author_name: str | None = None
    rating: float | None = None
    text: str
    matched_allergens: list[AllergyTag] = Field(default_factory=list)
    signal_type: SignalType
    impact: ImpactDirection
    excerpt: str
    weight: float
    publish_time: str | None = None


class PlaceDetailsResponse(BaseModel):
    id: str
    name: str
    address: str | None = None
    location: LatLng
    rating: float | None = None
    user_rating_count: int | None = None
    primary_type: str | None = None
    website_uri: str | None = None
    editorial_summary: str | None = None
    national_phone_number: str | None = None
    international_phone_number: str | None = None
    price_level: str | None = None
    price_range: str | None = None
    regular_opening_hours: dict | None = None
    current_opening_hours: dict | None = None
    service_options: dict[str, bool | None] = Field(default_factory=dict)
    google_maps_uri: str
    google_review_uri: str
    selected_allergens: list[AllergyTag]
    score_summary: PlaceScoreSummary
    evidence: list[ReviewEvidence]
    review_snippets: list["PlaceReviewSnippet"] = Field(default_factory=list)
    review_source_summary: "ReviewSourceSummary | None" = None
    photos: list["PlacePhoto"] = Field(default_factory=list)
    explanation: str
    menu: "PlaceMenu | None" = None
    recommended_items: list["RecommendedMenuItem"] = Field(default_factory=list)
    community_reviews: list["CommunityReview"] = Field(default_factory=list)
    agent_recommendation: "RecommendationResult | None" = None


class MenuItem(BaseModel):
    name: str
    description: str | None = None
    price: str | None = None
    confirmed_allergens: list[AllergyTag] = Field(default_factory=list)
    inferred_risks: list[AllergyTag] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    verification_status: str = "inferred"


class MenuSection(BaseModel):
    title: str
    items: list[MenuItem] = Field(default_factory=list)


class PlaceMenu(BaseModel):
    place_id: str | None = None
    source_url: str | None = None
    source_fetched_at: str | None = None
    status: str = "missing"
    sections: list[MenuSection] = Field(default_factory=list)


class MenuSource(BaseModel):
    source_type: SourceType = SourceType.UNKNOWN
    source_url: str | None = None
    source_timestamp: str | None = None
    reliability: float = Field(default=0.5, ge=0, le=1)
    raw_text: str | None = None
    sections: list[MenuSection] = Field(default_factory=list)
    content_type: str | None = None
    document_url: str | None = None
    extraction_method: str | None = None
    page_count: int | None = Field(default=None, ge=0)
    extraction_confidence: float | None = Field(default=None, ge=0, le=1)


class EvidenceFragment(BaseModel):
    id: str
    source_type: SourceType
    text: str
    source_url: str | None = None
    source_timestamp: str | None = None
    dish_name: str | None = None
    matched_allergens: list[AllergyTag] = Field(default_factory=list)
    reliability: float = Field(default=0.5, ge=0, le=1)


class DishRiskResult(BaseModel):
    dish: str
    risk_level: RiskLevel
    confidence: float = Field(ge=0, le=1)
    detected_allergens: list[AllergyTag] = Field(default_factory=list)
    evidence: list[EvidenceFragment] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    recommended_questions: list[str] = Field(default_factory=list)
    recommended_action: RecommendedAction


class AgentTraceSummary(BaseModel):
    nodes: list[str] = Field(default_factory=list)
    tool_calls: list[str] = Field(default_factory=list)
    abstained: bool = False
    routed_to_safety_gate: bool = False


class RecommendationResult(BaseModel):
    restaurant_id: str | None = None
    restaurant_name: str | None = None
    profile: AllergyProfile = Field(default_factory=AllergyProfile)
    overall_risk: RiskLevel
    confidence: float = Field(ge=0, le=1)
    summary: str
    dish_results: list[DishRiskResult] = Field(default_factory=list)
    evidence: list[EvidenceFragment] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    recommended_questions: list[str] = Field(default_factory=list)
    recommended_action: RecommendedAction
    trace: AgentTraceSummary = Field(default_factory=AgentTraceSummary)


class RestaurantContext(BaseModel):
    restaurant_id: str | None = None
    restaurant_name: str | None = None
    website_url: str | None = None
    location: LatLng | None = None
    menu_sources: list[MenuSource] = Field(default_factory=list)
    review_evidence: list[EvidenceFragment] = Field(default_factory=list)


class AnalyzeMenuRequest(BaseModel):
    profile: AllergyProfile = Field(default_factory=AllergyProfile)
    restaurant_name: str | None = None
    menu_sources: list[MenuSource] = Field(default_factory=list)


class AnalyzeRestaurantRequest(BaseModel):
    profile: AllergyProfile = Field(default_factory=AllergyProfile)
    restaurant_id: str | None = None
    restaurant_name: str | None = None
    website_url: str | None = None
    context: RestaurantContext | None = None


class RecommendDishesRequest(BaseModel):
    profile: AllergyProfile = Field(default_factory=AllergyProfile)
    context: RestaurantContext


class ChatRequest(BaseModel):
    message: str
    profile: AllergyProfile = Field(default_factory=AllergyProfile)
    context: RestaurantContext | None = None


class FeedbackEvent(BaseModel):
    recommendation_id: str | None = None
    restaurant_id: str | None = None
    useful: bool | None = None
    correction: str | None = None
    created_at: str | None = None


class ChatResponse(BaseModel):
    answer: str
    recommendation: RecommendationResult


class FeedbackResponse(BaseModel):
    id: str
    status: str = "recorded"


class SearchIndexResponse(BaseModel):
    restaurant_id: str
    indexed_documents: int = 0
    status: str


class HybridSearchRequest(BaseModel):
    query: str = ""
    restaurant_id: str | None = None
    allergens: list[AllergyTag] = Field(default_factory=list)
    source_types: list[SourceType] = Field(default_factory=list)
    vector: list[float] | None = None
    top: int = Field(default=5, ge=1, le=20)


class HybridSearchResult(BaseModel):
    id: str
    restaurant_id: str
    restaurant_name: str | None = None
    dish_name: str | None = None
    menu_section: str | None = None
    source_type: SourceType
    source_url: str | None = None
    source_timestamp: str | None = None
    confidence: float = Field(default=0.5, ge=0, le=1)
    raw_text: str
    matched_allergens: list[AllergyTag] = Field(default_factory=list)
    retrieval_mode: str = "hybrid"
    can_support_low_risk: bool = False


class HybridSearchResponse(BaseModel):
    query: str
    results: list[HybridSearchResult] = Field(default_factory=list)


class RecommendedMenuItem(BaseModel):
    name: str
    section_title: str | None = None
    reason: str
    caution: str | None = None
    source: str = "heuristic"


class CommunityReview(BaseModel):
    id: str
    author_name: str
    body: str
    created_at: str
    verification_status: str = "unverified"


class PlaceReviewSnippet(BaseModel):
    review_id: str
    author_name: str | None = None
    rating: float | None = None
    text: str
    publish_time: str | None = None
    relative_publish_time: str | None = None


class ReviewSourceSummary(BaseModel):
    google_review_count: int = 0
    expanded_review_count: int = 0
    local_snapshot_review_count: int = 0
    analyzed_review_count: int = 0
    displayed_review_count: int = 0
    expanded_reviews_configured: bool = False
    expanded_review_provider: str | None = None


class PlacePhoto(BaseModel):
    name: str
    url: str
    width_px: int | None = None
    height_px: int | None = None
    author_names: list[str] = Field(default_factory=list)


class MenuRefreshJob(BaseModel):
    id: str
    place_id: str
    status: str = "queued"
    message: str
    created_at: str
    completed_at: str | None = None


class ReviewRefreshJob(BaseModel):
    id: str
    place_id: str
    status: str = "queued"
    message: str
    reviews_count: int = 0
    created_at: str
    completed_at: str | None = None


class AskRestaurantRequest(BaseModel):
    place_id: str
    place_name: str | None = None
    allergens: list[AllergyTag] = Field(default_factory=list)
    question: str | None = None


class AskRestaurantResponse(BaseModel):
    id: str
    status: str = "queued"
    message: str
    suggested_script: str


class UserProfileResponse(BaseModel):
    authenticated: bool = False
    profile: AllergyProfile = Field(default_factory=AllergyProfile)
    saved_places: list[str] = Field(default_factory=list)


PlaceDetailsResponse.model_rebuild()
