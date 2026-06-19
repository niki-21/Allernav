from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from .agent_graph import run_dining_safety_graph
from .models import (
    AnalyzeMenuRequest,
    AnalyzeRestaurantRequest,
    AllergyProfile,
    ChatRequest,
    ChatResponse,
    EvidenceFragment,
    FeedbackEvent,
    FeedbackResponse,
    RecommendationResult,
    RecommendDishesRequest,
    RestaurantContext,
)


FEEDBACK_EVENTS: dict[str, FeedbackEvent] = {}


async def analyze_menu_service(payload: AnalyzeMenuRequest) -> RecommendationResult:
    context = RestaurantContext(
        restaurant_name=payload.restaurant_name,
        menu_sources=payload.menu_sources,
    )
    return run_dining_safety_graph(profile=payload.profile, restaurant_name=payload.restaurant_name, context=context)


async def analyze_restaurant_service(payload: AnalyzeRestaurantRequest) -> RecommendationResult:
    context = payload.context
    if context is None and (payload.restaurant_id or payload.restaurant_name or payload.website_url):
        context = RestaurantContext(
            restaurant_id=payload.restaurant_id,
            restaurant_name=payload.restaurant_name,
            website_url=payload.website_url,
        )
    elif context is not None and payload.website_url and not context.website_url:
        context = context.model_copy(update={"website_url": payload.website_url})

    return run_dining_safety_graph(
        profile=payload.profile,
        restaurant_id=payload.restaurant_id,
        restaurant_name=payload.restaurant_name,
        context=context,
    )


async def recommend_dishes_service(payload: RecommendDishesRequest) -> RecommendationResult:
    return run_dining_safety_graph(profile=payload.profile, context=payload.context)


async def chat_service(payload: ChatRequest) -> ChatResponse:
    result = run_dining_safety_graph(profile=payload.profile, context=payload.context)
    answer = (
        f"{result.summary} Recommended action: {result.recommended_action.value.replace('_', ' ')}. "
        "This is decision support, not a guarantee; verify ingredients and cross-contact handling with restaurant staff."
    )
    return ChatResponse(answer=answer, recommendation=result)


async def feedback_service(payload: FeedbackEvent) -> FeedbackResponse:
    event_id = str(uuid4())
    created_at = payload.created_at or datetime.now(UTC).isoformat()
    FEEDBACK_EVENTS[event_id] = payload.model_copy(update={"created_at": created_at})
    return FeedbackResponse(id=event_id)


async def restaurant_evidence_service(restaurant_id: str) -> list[EvidenceFragment]:
    result = run_dining_safety_graph(profile=AllergyProfile(), restaurant_id=restaurant_id)
    return result.evidence
