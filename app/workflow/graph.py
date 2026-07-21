from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.workflow.state import ResearchRoute, ResearchState


def initialize_node(_: ResearchState) -> dict[str, str]:
    """Initialize the workflow status for a new request."""

    return {
        "status": "initialized",
    }


def classify_route(query: str) -> ResearchRoute:
    """Classify a query using a minimal deterministic rule."""

    normalized_query = query.strip().lower()

    deep_research_keywords = (
        "compare",
        "research",
        "analyze",
        "latest",
        "sources",
        "evidence",
    )

    if any(keyword in normalized_query for keyword in deep_research_keywords):
        return "deep_research"

    return "direct"


def route_node(state: ResearchState) -> dict[str, ResearchRoute | str]:
    """Choose the workflow path for the current query."""

    route = classify_route(state["query"])

    return {
        "route": route,
        "status": "routed",
    }


def select_route(
    state: ResearchState,
) -> Literal["direct_answer", "deep_research"]:
    """Select the next graph node from the routing decision."""

    if state["route"] == "direct":
        return "direct_answer"

    return "deep_research"


def direct_answer_node(_: ResearchState) -> dict[str, str]:
    """Mark a simple request as ready for direct answering."""

    return {
        "status": "direct_answer_ready",
    }


def deep_research_node(_: ResearchState) -> dict[str, str]:
    """Mark a complex request as ready for the research workflow."""

    return {
        "status": "deep_research_ready",
    }


def build_research_graph() -> CompiledStateGraph:
    """Build and compile the research routing workflow."""

    graph_builder = StateGraph(ResearchState)

    graph_builder.add_node("initialize", initialize_node)
    graph_builder.add_node("route", route_node)
    graph_builder.add_node("direct_answer", direct_answer_node)
    graph_builder.add_node("deep_research", deep_research_node)

    graph_builder.add_edge(START, "initialize")
    graph_builder.add_edge("initialize", "route")

    graph_builder.add_conditional_edges(
        "route",
        select_route,
        {
            "direct_answer": "direct_answer",
            "deep_research": "deep_research",
        },
    )

    graph_builder.add_edge("direct_answer", END)
    graph_builder.add_edge("deep_research", END)

    return graph_builder.compile()


research_graph = build_research_graph()