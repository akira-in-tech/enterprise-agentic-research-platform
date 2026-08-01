from collections.abc import Awaitable, Callable
from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.analyst import AnalystAgent
from app.agents.direct_answer import DirectAnswerAgent
from app.agents.intent_router import IntentRouter
from app.agents.planner import PlannerAgent
from app.agents.reflection import ReflectionAgent
from app.schemas.evidence import (
    CitationAudit,
    EvidenceScore,
    EvidenceSource,
    ReflectionDecision,
)
from app.schemas.intent import IntentDecision
from app.schemas.planner import ResearchPlan
from app.schemas.source import WebSource
from app.services.evidence import (
    CitationValidator,
    EvidenceScorer,
    normalize_web_sources,
)
from app.services.llm.base import LLMClient
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
EvidenceAnalyzer = Callable[
    [str, list[WebSource]],
    tuple[list[EvidenceSource], list[EvidenceScore]],
]
ReportGenerator = Callable[
    [
        str,
        ResearchPlan,
        list[EvidenceSource],
        list[EvidenceScore],
        str | None,
        ReflectionDecision | None,
    ],
    Awaitable[str],
]
ReportReviewer = Callable[
    [str, list[EvidenceSource], list[EvidenceScore]],
    tuple[CitationAudit, ReflectionDecision],
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


def build_evidence_node(
    analyze_evidence: EvidenceAnalyzer,
) -> Callable[[ResearchState], dict[str, object]]:
    """Create the deterministic evidence-scoring node."""

    def evidence_node(state: ResearchState) -> dict[str, object]:
        sources, scores = analyze_evidence(
            state["query"],
            state.get("web_sources", []),
        )

        return {
            "evidence_sources": sources,
            "evidence_scores": scores,
            "status": "evidence_scored",
        }

    return evidence_node


def build_analyst_node(
    generate_report: ReportGenerator,
) -> Callable[[ResearchState], Awaitable[dict[str, object]]]:
    """Create the evidence-backed analyst node."""

    async def analyst_node(state: ResearchState) -> dict[str, object]:
        report = await generate_report(
            state["query"],
            state["plan"],
            state["evidence_sources"],
            state["evidence_scores"],
            state.get("report"),
            state.get("reflection"),
        )

        return {
            "report": report,
            "reflection_attempts": state.get("reflection_attempts", 0) + 1,
            "status": "report_generated",
        }

    return analyst_node


def build_reflection_node(
    review_report: ReportReviewer,
) -> Callable[[ResearchState], dict[str, object]]:
    """Create the citation and evidence quality-gate node."""

    def reflection_node(state: ResearchState) -> dict[str, object]:
        audit, decision = review_report(
            state["report"],
            state["evidence_sources"],
            state["evidence_scores"],
        )

        return {
            "answer": state["report"],
            "citation_audit": audit,
            "reflection": decision,
            "status": (
                "research_report_completed"
                if decision.status == "approved"
                else "research_report_revision_required"
            ),
        }

    return reflection_node


def select_reflection_path(
    state: ResearchState,
    *,
    max_attempts: int,
) -> Literal["revise", "complete"]:
    """Bound report revision while allowing one evidence-guided retry."""

    if (
        state["reflection"].status == "revise"
        and state.get("reflection_attempts", 0) < max_attempts
    ):
        return "revise"

    return "complete"


def build_research_graph(
    classifier: IntentClassifier,
    create_plan: PlanCreator,
    generate_direct_answer: DirectAnswerGenerator,
    execute_search: SearchPlanExecutor,
    *,
    analyze_evidence: EvidenceAnalyzer | None = None,
    generate_report: ReportGenerator | None = None,
    review_report: ReportReviewer | None = None,
    max_reflection_attempts: int = 2,
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

    quality_pipeline = (
        analyze_evidence is not None and generate_report is not None and review_report is not None
    )

    if (
        any(
            item is not None
            for item in (
                analyze_evidence,
                generate_report,
                review_report,
            )
        )
        and not quality_pipeline
    ):
        raise ValueError(
            "The evidence, analyst, and reflection callbacks must be provided together."
        )

    if quality_pipeline:
        if max_reflection_attempts < 1:
            raise ValueError("max_reflection_attempts must be at least 1.")

        assert analyze_evidence is not None
        assert generate_report is not None
        assert review_report is not None
        graph_builder.add_node(  # type: ignore[call-overload]
            "evidence",
            build_evidence_node(analyze_evidence),
        )
        graph_builder.add_node(  # type: ignore[call-overload]
            "analyst",
            build_analyst_node(generate_report),
        )
        graph_builder.add_node(  # type: ignore[call-overload]
            "reflection",
            build_reflection_node(review_report),
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
    if quality_pipeline:
        graph_builder.add_edge("web_search", "evidence")
        graph_builder.add_edge("evidence", "analyst")
        graph_builder.add_edge("analyst", "reflection")
        graph_builder.add_conditional_edges(
            "reflection",
            lambda state: select_reflection_path(
                state,
                max_attempts=max_reflection_attempts,
            ),
            {
                "revise": "analyst",
                "complete": END,
            },
        )
    else:
        graph_builder.add_edge("web_search", END)

    return graph_builder.compile()


def build_research_graph_for_client(
    llm_client: LLMClient,
) -> ResearchGraph:
    """Build the production graph around one supplied LLM client."""

    tavily_client = TavilySearchClient()

    intent_router = IntentRouter(llm_client)
    direct_answer_agent = DirectAnswerAgent(llm_client)
    planner = PlannerAgent(llm_client)
    search_executor = SearchExecutor(tavily_client)
    evidence_scorer = EvidenceScorer()
    analyst = AnalystAgent(llm_client)
    citation_validator = CitationValidator()
    reflection = ReflectionAgent()

    def analyze_evidence(
        query: str,
        sources: list[WebSource],
    ) -> tuple[list[EvidenceSource], list[EvidenceScore]]:
        normalized_sources = normalize_web_sources(sources)

        return normalized_sources, evidence_scorer.score(
            query=query,
            sources=normalized_sources,
        )

    async def generate_report(
        query: str,
        plan: ResearchPlan,
        sources: list[EvidenceSource],
        scores: list[EvidenceScore],
        previous_report: str | None,
        revision_feedback: ReflectionDecision | None,
    ) -> str:
        return await analyst.write_report(
            query=query,
            plan=plan,
            sources=sources,
            scores=scores,
            previous_report=previous_report,
            revision_feedback=revision_feedback,
        )

    def review_report(
        report: str,
        sources: list[EvidenceSource],
        scores: list[EvidenceScore],
    ) -> tuple[CitationAudit, ReflectionDecision]:
        audit = citation_validator.validate(
            report=report,
            sources=sources,
        )

        return audit, reflection.review(
            citation_audit=audit,
            evidence_scores=scores,
        )

    return build_research_graph(
        intent_router.classify,
        planner.create_plan,
        direct_answer_agent.answer,
        search_executor.execute,
        analyze_evidence=analyze_evidence,
        generate_report=generate_report,
        review_report=review_report,
    )


def build_default_research_graph(
    provider: str | None = None,
) -> ResearchGraph:
    """Build the production graph for one selected provider."""

    llm_client = create_llm_client(
        provider,
    )

    return build_research_graph_for_client(
        llm_client,
    )
