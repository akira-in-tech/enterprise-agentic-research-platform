from collections.abc import Awaitable, Callable
from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.direct_answer import DirectAnswerAgent
from app.agents.intent_router import IntentRouter
from app.agents.planner import PlannerAgent
from app.schemas.intent import IntentDecision
from app.schemas.planner import ResearchPlan
from app.services.llm.factory import create_llm_client
from app.services.search.executor import (
    ResearchTaskResult,
    SearchExecutor,
)
from app.services.search.results import build_web_source_pool
from app.services.search.tavily import TavilySearchClient
from app.workflow.state import ResearchState

IntentClassifier = Callable[[str], Awaitable[IntentDecision]]
PlanCreator = Callable[[str], Awaitable[ResearchPlan]]
DirectAnswerGenerator = Callable[[str], Awaitable[str]]
SearchPlanExecutor = Callable[
    [ResearchPlan],
    Awaitable[list[ResearchTaskResult]],
]

ResearchGraph = CompiledStateGraph[
    ResearchState,
    None,
    ResearchState,
    ResearchState,
]


def initialize_node(_: ResearchState) -> dict[str, str]:
    """Initialize the workflow status for a new request."""

    return {"status": "initialized"}


def build_route_node(
    classifier: IntentClassifier,
) -> Callable[[ResearchState], Awaitable[dict[str, str]]]:
    """Create the asynchronous route node."""

    async def route_node(
        state: ResearchState,
    ) -> dict[str, str]:
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


def build_direct_answer_node(
    generate_answer: DirectAnswerGenerator,
) -> Callable[[ResearchState], Awaitable[dict[str, str]]]:
    """Create the asynchronous direct-answer node."""

    async def direct_answer_node(
        state: ResearchState,
    ) -> dict[str, str]:
        answer = await generate_answer(state["query"])

        return {
            "answer": answer,
            "status": "direct_answer_completed",
        }

    return direct_answer_node


def build_planner_node(
    create_plan: PlanCreator,
) -> Callable[
    [ResearchState],
    Awaitable[dict[str, object]],
]:
    """Create the asynchronous planner node."""

    async def planner_node(
        state: ResearchState,
    ) -> dict[str, object]:
        plan = await create_plan(state["query"])

        return {
            "plan": plan,
            "status": "research_plan_ready",
        }

    return planner_node


def build_web_search_node(
    execute_search: SearchPlanExecutor,
) -> Callable[
    [ResearchState],
    Awaitable[dict[str, object]],
]:
    """Create the asynchronous web-search node."""

    async def web_search_node(
        state: ResearchState,
    ) -> dict[str, object]:
        outcomes = await execute_search(state["plan"])

        web_sources = build_web_source_pool(
            result for outcome in outcomes for result in outcome.results
        )

        succeeded_count = sum(outcome.succeeded for outcome in outcomes)
        empty_success_count = sum(outcome.succeeded and not outcome.results for outcome in outcomes)

        if not outcomes or succeeded_count == 0:
            status = "web_search_failed"
        elif not web_sources:
            status = "web_search_empty"
        elif succeeded_count < len(outcomes) or empty_success_count > 0:
            status = "web_search_partial"
        else:
            status = "web_search_completed"

        return {
            "web_search_results": outcomes,
            "web_sources": web_sources,
            "status": status,
        }

    return web_search_node


def build_research_graph(
    classifier: IntentClassifier,
    create_plan: PlanCreator,
    generate_direct_answer: DirectAnswerGenerator,
    execute_search: SearchPlanExecutor,
) -> ResearchGraph:
    """Build and compile the answering and research workflow."""

    graph_builder = StateGraph(ResearchState)

    graph_builder.add_node(  # type: ignore[call-overload]
        "initialize",
        initialize_node,
    )
    graph_builder.add_node(  # type: ignore[call-overload]
        "route",
        build_route_node(classifier),
    )
    graph_builder.add_node(  # type: ignore[call-overload]
        "direct_answer",
        build_direct_answer_node(generate_direct_answer),
    )
    graph_builder.add_node(  # type: ignore[call-overload]
        "planner",
        build_planner_node(create_plan),
    )
    graph_builder.add_node(  # type: ignore[call-overload]
        "web_search",
        build_web_search_node(execute_search),
    )

    graph_builder.add_edge(
        START,
        "initialize",
    )
    graph_builder.add_edge(
        "initialize",
        "route",
    )

    graph_builder.add_conditional_edges(
        "route",
        select_route,
        {
            "direct_answer": "direct_answer",
            "planner": "planner",
        },
    )

    graph_builder.add_edge(
        "direct_answer",
        END,
    )
    graph_builder.add_edge(
        "planner",
        "web_search",
    )
    graph_builder.add_edge(
        "web_search",
        END,
    )

    return graph_builder.compile()


def build_default_research_graph(
    provider: str | None = None,
) -> ResearchGraph:
    """Build the production graph for one selected provider."""

    llm_client = create_llm_client(
        provider,
    )
    tavily_client = TavilySearchClient()

    intent_router = IntentRouter(llm_client)
    direct_answer_agent = DirectAnswerAgent(llm_client)
    planner = PlannerAgent(llm_client)
    search_executor = SearchExecutor(tavily_client)

    return build_research_graph(
        intent_router.classify,
        planner.create_plan,
        direct_answer_agent.answer,
        search_executor.execute,
    )
