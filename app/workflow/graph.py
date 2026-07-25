from collections.abc import Awaitable, Callable
from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.intent_router import IntentRouter
from app.agents.planner import PlannerAgent
from app.schemas.intent import IntentDecision
from app.schemas.planner import ResearchPlan
from app.services.llm.anthropic import AnthropicClient
from app.workflow.state import ResearchState

IntentClassifier = Callable[[str], Awaitable[IntentDecision]]
PlanCreator = Callable[[str], Awaitable[ResearchPlan]]


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
) -> Literal["direct_answer", "planner"]:
    """Select the next node from the route stored in state."""

    if state["route"] == "direct":
        return "direct_answer"

    return "planner"


def direct_answer_node(_: ResearchState) -> dict[str, str]:
    """Mark the request as ready for direct answering."""

    return {"status": "direct_answer_ready"}


def build_planner_node(
    create_plan: PlanCreator,
) -> Callable[[ResearchState], Awaitable[dict[str, object]]]:
    """Create the asynchronous planner node."""

    async def planner_node(state: ResearchState) -> dict[str, object]:
        plan = await create_plan(state["query"])

        return {
            "plan": plan,
            "status": "research_plan_ready",
        }

    return planner_node


def build_research_graph(
    classifier: IntentClassifier,
    create_plan: PlanCreator,
) -> CompiledStateGraph:
    """Build and compile the intent-routing and planning workflow."""

    graph_builder = StateGraph(ResearchState)

    graph_builder.add_node("initialize", initialize_node)
    graph_builder.add_node("route", build_route_node(classifier))
    graph_builder.add_node("direct_answer", direct_answer_node)
    graph_builder.add_node("planner", build_planner_node(create_plan))

    graph_builder.add_edge(START, "initialize")
    graph_builder.add_edge("initialize", "route")

    graph_builder.add_conditional_edges(
        "route",
        select_route,
        {
            "direct_answer": "direct_answer",
            "planner": "planner",
        },
    )

    graph_builder.add_edge("direct_answer", END)
    graph_builder.add_edge("planner", END)

    return graph_builder.compile()


def build_default_research_graph() -> CompiledStateGraph:
    """Build the production graph with Claude-backed agents."""

    anthropic_client = AnthropicClient()
    intent_router = IntentRouter(anthropic_client)
    planner = PlannerAgent(anthropic_client)

    return build_research_graph(
        intent_router.classify,
        planner.create_plan,
    )


research_graph = build_default_research_graph()