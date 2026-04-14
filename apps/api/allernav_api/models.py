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
    positive_signals: list[str] = Field(default_factory=list)
    negative_signals: list[str] = Field(default_factory=list)
    evidence_count: int = Field(default=0, ge=0)


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
    selected_allergens: list[AllergyTag]
    score_summary: PlaceScoreSummary
    evidence: list[ReviewEvidence]
    explanation: str

