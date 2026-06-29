from __future__ import annotations

from typing import Any, TypedDict

try:
    from langsmith import traceable
except ImportError:  # pragma: no cover - keeps local installs usable before optional tracing deps are installed
    def traceable(*args: Any, **_kwargs: Any) -> Any:
        if args and callable(args[0]):
            return args[0]

        def decorator(func: Any) -> Any:
            return func

        return decorator

from .fixtures import get_fixture_context
from .langchain_tracing import update_current_trace_metadata
from .menu_ingestion import ingest_menu_from_website, load_menu_source
from .models import (
    AgentTraceSummary,
    AllergyProfile,
    RecommendationResult,
    RestaurantContext,
)
from .risk_engine import analyze_restaurant_context


class DiningAgentState(TypedDict, total=False):
    profile: AllergyProfile
    restaurant_id: str | None
    restaurant_name: str | None
    context: RestaurantContext | None
    result: RecommendationResult
    trace: AgentTraceSummary


GRAPH_NODES = [
    "intent_profile_parser",
    "restaurant_menu_retrieval",
    "menu_normalization",
    "allergen_risk_engine",
    "evidence_selector",
    "explanation_builder",
    "safety_confidence_gate",
]


@traceable(name="AllerNav Dining Safety Graph", run_type="chain")
def run_dining_safety_graph(
    *,
    profile: AllergyProfile,
    restaurant_id: str | None = None,
    restaurant_name: str | None = None,
    context: RestaurantContext | None = None,
) -> RecommendationResult:
    initial_state: DiningAgentState = {
        "profile": profile,
        "restaurant_id": restaurant_id,
        "restaurant_name": restaurant_name,
        "context": context,
        "trace": AgentTraceSummary(),
    }

    try:
        graph = build_langgraph()
    except ImportError:
        final_state = run_sequential_graph(initial_state)
    else:
        final_state = graph.invoke(
            initial_state,
            config={
                "run_name": "AllerNav LangGraph",
                "tags": ["allernav", "dining-safety", "langgraph"],
                "metadata": {
                    "restaurant_id": restaurant_id,
                    "restaurant_name": restaurant_name,
                    "allergens": [allergen.value for allergen in profile.allergens],
                    "has_context": context is not None,
                    "menu_source_count": len(context.menu_sources) if context else 0,
                },
            },
        )

    return final_state["result"]


def build_langgraph() -> Any:
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(DiningAgentState)
    graph.add_node("intent_profile_parser", intent_profile_parser)
    graph.add_node("restaurant_menu_retrieval", restaurant_menu_retrieval)
    graph.add_node("menu_normalization", menu_normalization)
    graph.add_node("allergen_risk_engine", allergen_risk_engine)
    graph.add_node("evidence_selector", evidence_selector)
    graph.add_node("explanation_builder", explanation_builder)
    graph.add_node("safety_confidence_gate", safety_confidence_gate)

    graph.add_edge(START, "intent_profile_parser")
    graph.add_edge("intent_profile_parser", "restaurant_menu_retrieval")
    graph.add_edge("restaurant_menu_retrieval", "menu_normalization")
    graph.add_edge("menu_normalization", "allergen_risk_engine")
    graph.add_edge("allergen_risk_engine", "evidence_selector")
    graph.add_edge("evidence_selector", "explanation_builder")
    graph.add_edge("explanation_builder", "safety_confidence_gate")
    graph.add_edge("safety_confidence_gate", END)
    return graph.compile()


def run_sequential_graph(state: DiningAgentState) -> DiningAgentState:
    for node in (
        intent_profile_parser,
        restaurant_menu_retrieval,
        menu_normalization,
        allergen_risk_engine,
        evidence_selector,
        explanation_builder,
        safety_confidence_gate,
    ):
        state.update(node(state))
    return state


def intent_profile_parser(state: DiningAgentState) -> DiningAgentState:
    trace = state.get("trace") or AgentTraceSummary()
    trace.nodes.append("Intent & Profile Parser")
    profile = state.get("profile") or AllergyProfile()
    return {"profile": profile, "trace": trace}


def restaurant_menu_retrieval(state: DiningAgentState) -> DiningAgentState:
    trace = state.get("trace") or AgentTraceSummary()
    trace.nodes.append("Restaurant / Menu Retrieval")
    context = state.get("context")
    restaurant_id = state.get("restaurant_id") or (context.restaurant_id if context else None)
    restaurant_name = state.get("restaurant_name") or (context.restaurant_name if context else None)

    if context and context.menu_sources:
        trace.tool_calls.append("provided_menu_context")
        return {"context": context, "trace": trace}

    stored_menu = load_menu_source(restaurant_id) if restaurant_id else None
    if stored_menu:
        trace.tool_calls.append("stored_menu_lookup")
        context = context or RestaurantContext(restaurant_id=restaurant_id, restaurant_name=restaurant_name)
        context = context.model_copy(update={"menu_sources": [stored_menu, *context.menu_sources]})
        return {"context": context, "trace": trace}

    website_url = context.website_url if context else None
    if restaurant_id and website_url:
        ingested = ingest_menu_from_website(
            restaurant_id=restaurant_id,
            restaurant_name=restaurant_name,
            website_url=website_url,
        )
        trace.tool_calls.append("official_menu_ingestion")
        if ingested.sections:
            context = context or RestaurantContext(restaurant_id=restaurant_id, restaurant_name=restaurant_name)
            context = context.model_copy(update={"menu_sources": [ingested, *context.menu_sources]})
            return {"context": context, "trace": trace}

    if context is None:
        context = get_fixture_context(restaurant_id, restaurant_name)
        if context is not None:
            trace.tool_calls.append("fixture_menu_lookup")

    if context is None:
        context = RestaurantContext(
            restaurant_id=restaurant_id,
            restaurant_name=restaurant_name,
        )

    if not context.menu_sources:
        trace.tool_calls.append("menu_evidence_not_found")
    return {"context": context, "trace": trace}


def menu_normalization(state: DiningAgentState) -> DiningAgentState:
    trace = state.get("trace") or AgentTraceSummary()
    trace.nodes.append("Menu Extraction & Normalization")
    return {"trace": trace}


def allergen_risk_engine(state: DiningAgentState) -> DiningAgentState:
    trace = state.get("trace") or AgentTraceSummary()
    trace.nodes.append("Allergen Risk Engine")
    result = analyze_restaurant_context(
        context=state.get("context") or RestaurantContext(),
        profile=state.get("profile") or AllergyProfile(),
        trace=trace,
    )
    return {"result": result, "trace": result.trace}


def evidence_selector(state: DiningAgentState) -> DiningAgentState:
    trace = state.get("trace") or AgentTraceSummary()
    trace.nodes.append("Evidence Retrieval")
    result = state["result"]
    result.trace = trace
    return {"result": result, "trace": trace}


def explanation_builder(state: DiningAgentState) -> DiningAgentState:
    trace = state.get("trace") or AgentTraceSummary()
    trace.nodes.append("Recommendation + Explanation Generator")
    result = state["result"]
    result.trace = trace
    return {"result": result, "trace": trace}


def safety_confidence_gate(state: DiningAgentState) -> DiningAgentState:
    trace = state.get("trace") or AgentTraceSummary()
    trace.nodes.append("Safety / Confidence Gate")
    result = state["result"]
    result.trace = trace
    result.trace.routed_to_safety_gate = result.trace.routed_to_safety_gate or result.recommended_action.value != "verify"
    result.trace.abstained = result.recommended_action.value == "insufficient_evidence"
    context = state.get("context")
    item_count = sum(len(section.items) for source in context.menu_sources for section in source.sections) if context else 0
    update_current_trace_metadata(
        restaurant_id=state.get("restaurant_id") or (context.restaurant_id if context else None),
        source_url=context.menu_sources[0].source_url if context and context.menu_sources else None,
        item_count=item_count,
        allergens=[allergen.value for allergen in (state.get("profile") or AllergyProfile()).allergens],
        safety_gate=result.recommended_action.value,
        retrieval_mode="stored_or_official_menu",
    )
    return {"result": result, "trace": trace}
