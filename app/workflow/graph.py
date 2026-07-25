from collections.abc import Awaitable, Callable
from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.intent_router import IntentRouter
from app.schemas.intent import IntentDecision
from app.services.claude import ClaudeClient
from app.workflow.state import ResearchState

IntentClassifier = Callable[[str], Awaitable[IntentDecision]]


def initialize_node(_: ResearchState) -> dict[str, str]:
    """Initialize the workflow status for a new request."""

    return {"status": "initialized"}


def build_route_node(
    classifier: IntentClassifier,
) -> Callable[[ResearchState], Awaitable[dict[str, str]]]:
    """Create the asynchronous route node."""

    async def route_node(state: ResearchState) -> dict[str, str]:
        decision = await classifier(state["query"])

        return {
            "route": decision.route,
            "route_reason": decision.reason,
            "status": "routed",
        }

    return route_node


def select_route(
    state: ResearchState,
) -> Literal["direct_answer", "deep_research"]:
    """Select the next node from the route stored in state."""

    if state["route"] == "direct":
        return "direct_answer"

    return "deep_research"


def direct_answer_node(_: ResearchState) -> dict[str, str]:
    """Mark the request as ready for direct answering."""

    return {"status": "direct_answer_ready"}


def deep_research_node(_: ResearchState) -> dict[str, str]:
    """Mark the request as ready for deep research."""

    return {"status": "deep_research_ready"}


def build_research_graph(
    classifier: IntentClassifier,
) -> CompiledStateGraph:
    """Build and compile the asynchronous routing workflow."""

    graph_builder = StateGraph(ResearchState)

    graph_builder.add_node("initialize", initialize_node)
    graph_builder.add_node("route", build_route_node(classifier))
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


def build_default_research_graph() -> CompiledStateGraph:
    """Build the production graph with the Claude Intent Router."""

    claude_client = ClaudeClient()
    intent_router = IntentRouter(claude_client)

    return build_research_graph(intent_router.classify)


research_graph = build_default_research_graph()