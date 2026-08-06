from collections.abc import Awaitable, Callable, Sequence
from typing import Literal, Protocol
from uuid import UUID

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from tavily.errors import TimeoutError as TavilyTimeoutError  # type: ignore[import-untyped]

from app.agents.analyst import AnalystAgent
from app.agents.direct_answer import DirectAnswerAgent
from app.agents.evidence_judge import EvidenceJudgeAgent, EvidenceJudgeResult
from app.agents.intent_router import IntentRouter
from app.agents.local_scout import LocalScoutAgent, LocalScoutResult
from app.agents.planner import PlannerAgent
from app.agents.reflection import ReflectionAgent
from app.agents.web_scout import WebScoutAgent, WebScoutResult
from app.agents.writer import WriterAgent
from app.core.circuit_breaker import CircuitBreaker
from app.schemas.evidence import (
    CitationAudit,
    EvidenceScore,
    EvidenceSource,
    ReflectionDecision,
)
from app.schemas.intent import IntentDecision
from app.schemas.planner import ResearchPlan, ResearchTask
from app.schemas.source import PrivateSource, WebSource
from app.schemas.workflow import (
    EvidenceGap,
    ReflectionResult,
    ResearchAnalysis,
)
from app.services.evidence import (
    CitationValidator,
    EvidenceScorer,
    normalize_web_sources,
)
from app.services.llm.base import LLMClient
from app.services.llm.factory import create_llm_client
from app.services.mcp import MCPReferenceScout
from app.services.search.executor import (
    DEFAULT_RETRYABLE_ERRORS,
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
LocalKnowledgeScout = Callable[
    [ResearchPlan, UUID],
    Awaitable[LocalScoutResult],
]
WebTaskScout = Callable[
    [Sequence[ResearchTask]],
    Awaitable[WebScoutResult],
]
LocalTaskScout = Callable[
    [Sequence[ResearchTask], UUID],
    Awaitable[LocalScoutResult],
]
MCPQueryScout = Callable[[str], Awaitable[list[EvidenceSource]]]


class EvidenceJudgeOperation(Protocol):
    async def __call__(
        self,
        *,
        query: str,
        web_sources: Sequence[WebSource],
        private_sources: Sequence[PrivateSource],
        additional_sources: Sequence[EvidenceSource] = (),
    ) -> EvidenceJudgeResult: ...


class AnalysisOperation(Protocol):
    async def __call__(
        self,
        *,
        query: str,
        sources: Sequence[EvidenceSource],
        scores: Sequence[EvidenceScore],
    ) -> ResearchAnalysis: ...


class ReflectionOperation(Protocol):
    async def __call__(
        self,
        *,
        analysis: ResearchAnalysis,
        evidence_gaps: Sequence[EvidenceGap],
        attempted_queries: Sequence[str],
    ) -> ReflectionResult: ...


class WriterOperation(Protocol):
    async def __call__(
        self,
        *,
        query: str,
        plan: ResearchPlan,
        analysis: ResearchAnalysis,
        sources: Sequence[EvidenceSource],
        scores: Sequence[EvidenceScore],
        previous_report: str | None = None,
        revision_feedback: ReflectionDecision | None = None,
    ) -> str: ...


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
    [str, list[EvidenceSource], list[EvidenceScore], bool],
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
) -> Callable[[ResearchState], Awaitable[dict[str, object]]]:
    """Create the asynchronous route node."""

    async def route_node(
        state: ResearchState,
    ) -> dict[str, object]:
        decision = await classifier(state["query"])

        return {
            "route": decision.route,
            "route_reason": decision.reason,
            "is_high_risk_domain": decision.is_high_risk_domain,
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


def build_local_scout_node(
    scout_private_knowledge: LocalKnowledgeScout,
) -> Callable[[ResearchState], Awaitable[dict[str, object]]]:
    """Create the tenant-scoped Local Scout node."""

    async def local_scout_node(state: ResearchState) -> dict[str, object]:
        tenant_id = state.get("tenant_id")

        if tenant_id is None:
            raise ValueError("Local Scout requires tenant_id in ResearchState.")

        result = await scout_private_knowledge(
            state["plan"],
            tenant_id,
        )

        if result.errors and not result.sources:
            status = "local_scout_failed"
        elif result.errors:
            status = "local_scout_partial"
        elif result.sources:
            status = "local_scout_completed"
        else:
            status = "local_scout_empty"

        return {
            "active_agent": "local_scout",
            "private_sources": result.sources,
            "local_scout_errors": result.errors,
            "status": status,
        }

    return local_scout_node


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
            state.get("is_high_risk_domain", False),
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
    scout_private_knowledge: LocalKnowledgeScout | None = None,
    analyze_evidence: EvidenceAnalyzer | None = None,
    generate_report: ReportGenerator | None = None,
    review_report: ReportReviewer | None = None,
    max_reflection_attempts: int = 2,
    checkpointer: BaseCheckpointSaver[str] | None = None,
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

    if scout_private_knowledge is not None:
        graph_builder.add_node(  # type: ignore[call-overload]
            "local_scout",
            build_local_scout_node(scout_private_knowledge),
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
    if scout_private_knowledge is None:
        graph_builder.add_edge(
            "planner",
            "web_search",
        )
    else:
        graph_builder.add_edge("planner", "local_scout")
        graph_builder.add_edge("local_scout", "web_search")
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

    return graph_builder.compile(checkpointer=checkpointer)


def _research_tasks_for_state(
    state: ResearchState,
    *,
    source: Literal["web", "private"],
) -> list[ResearchTask]:
    supplementary_queries = state.get("supplementary_queries", [])

    if state.get("iteration", 0) == 0 or not supplementary_queries:
        return list(state["plan"].tasks)

    return [
        ResearchTask(
            title=f"Follow-up {index}",
            search_query=item.query,
            rationale=item.reason,
        )
        for index, item in enumerate(supplementary_queries, start=1)
        if item.source_preference in {source, "hybrid"}
    ]


def _merge_web_sources(
    existing: Sequence[WebSource],
    new: Sequence[WebSource],
) -> list[WebSource]:
    merged: dict[str, WebSource] = {}

    for source in [*existing, *new]:
        merged[source.source_id] = source

    return list(merged.values())


def _merge_private_sources(
    existing: Sequence[PrivateSource],
    new: Sequence[PrivateSource],
) -> list[PrivateSource]:
    merged: dict[str, PrivateSource] = {}

    for source in [*existing, *new]:
        merged[source.source_id] = source

    return list(merged.values())


def _merge_evidence_sources(
    existing: Sequence[EvidenceSource],
    new: Sequence[EvidenceSource],
) -> list[EvidenceSource]:
    merged: dict[str, EvidenceSource] = {}
    for source in [*existing, *new]:
        merged[source.source_id] = source
    return list(merged.values())


def build_eight_agent_web_scout_node(
    scout_web: WebTaskScout,
    scout_mcp: MCPQueryScout | None = None,
) -> Callable[[ResearchState], Awaitable[dict[str, object]]]:
    """Create the canonical Web Scout node."""

    async def web_scout_node(state: ResearchState) -> dict[str, object]:
        tasks = _research_tasks_for_state(state, source="web")
        result = await scout_web(tasks)
        outcomes = [
            *state.get("web_search_results", []),
            *result.outcomes,
        ]
        sources = _merge_web_sources(
            state.get("web_sources", []),
            result.sources,
        )
        succeeded_count = sum(outcome.succeeded for outcome in result.outcomes)
        mcp_sources = state.get("mcp_sources", [])
        mcp_errors = state.get("mcp_scout_errors", [])

        if scout_mcp is None:
            mcp_status = "disabled"
        elif not tasks:
            mcp_status = "skipped"
        else:
            try:
                mcp_sources = _merge_evidence_sources(
                    mcp_sources,
                    await scout_mcp(state["query"]),
                )
                mcp_status = "completed" if mcp_sources else "empty"
            except Exception as error:
                mcp_errors = [*mcp_errors, str(error)]
                mcp_status = "failed"

        if not tasks:
            status = "skipped"
        elif not result.outcomes or succeeded_count == 0:
            status = "failed"
        elif succeeded_count < len(result.outcomes):
            status = "partial"
        elif result.sources:
            status = "completed"
        else:
            status = "empty"

        return {
            "web_search_results": outcomes,
            "web_sources": sources,
            "web_scout_status": status,
            "mcp_sources": mcp_sources,
            "mcp_scout_errors": mcp_errors,
            "mcp_scout_status": mcp_status,
        }

    return web_scout_node


def build_eight_agent_local_scout_node(
    scout_local: LocalTaskScout,
) -> Callable[[ResearchState], Awaitable[dict[str, object]]]:
    """Create the canonical Local Scout node."""

    async def local_scout_node(state: ResearchState) -> dict[str, object]:
        tenant_id = state.get("tenant_id")

        if tenant_id is None:
            raise ValueError("Local Scout requires tenant_id in ResearchState.")

        tasks = _research_tasks_for_state(state, source="private")
        result = await scout_local(tasks, tenant_id)
        sources = _merge_private_sources(
            state.get("private_sources", []),
            result.sources,
        )
        errors = [
            *state.get("local_scout_errors", []),
            *result.errors,
        ]

        if not tasks:
            status = "skipped"
        elif result.errors and not result.sources:
            status = "failed"
        elif result.errors:
            status = "partial"
        elif result.sources:
            status = "completed"
        else:
            status = "empty"

        return {
            "private_sources": sources,
            "local_scout_errors": errors,
            "local_scout_status": status,
        }

    return local_scout_node


def build_eight_agent_evidence_judge_node(
    judge_evidence: EvidenceJudgeOperation,
) -> Callable[[ResearchState], Awaitable[dict[str, object]]]:
    """Create the merged-source Evidence Judge node."""

    async def evidence_judge_node(state: ResearchState) -> dict[str, object]:
        additional_sources = [
            source for source in state.get("evidence_sources", []) if source.origin == "mcp"
        ]
        additional_sources = _merge_evidence_sources(
            additional_sources,
            state.get("mcp_sources", []),
        )
        result = await judge_evidence(
            query=state["query"],
            web_sources=state.get("web_sources", []),
            private_sources=state.get("private_sources", []),
            additional_sources=additional_sources,
        )

        return {
            "active_agent": "evidence_judge",
            "evidence_sources": result.sources,
            "evidence_scores": result.scores,
            "evidence_gaps": result.judgment.gaps,
            "evidence_conflicts": result.judgment.conflicts,
            "status": "evidence_judged",
        }

    return evidence_judge_node


def build_eight_agent_analyst_node(
    analyze: AnalysisOperation,
) -> Callable[[ResearchState], Awaitable[dict[str, object]]]:
    """Create the structured Analyst node."""

    async def analyst_node(state: ResearchState) -> dict[str, object]:
        analysis = await analyze(
            query=state["query"],
            sources=state["evidence_sources"],
            scores=state["evidence_scores"],
        )

        return {
            "active_agent": "analyst",
            "analysis": analysis,
            "analysis_findings": analysis.findings,
            "status": "analysis_completed",
        }

    return analyst_node


def build_eight_agent_reflect_node(
    reflect: ReflectionOperation,
) -> Callable[[ResearchState], Awaitable[dict[str, object]]]:
    """Create the bounded Reflect and supplementary-query node."""

    async def reflect_node(state: ResearchState) -> dict[str, object]:
        result = await reflect(
            analysis=state["analysis"],
            evidence_gaps=state.get("evidence_gaps", []),
            attempted_queries=state.get("attempted_queries", []),
        )
        iteration = state.get("iteration", 0)
        max_iterations = state.get("max_iterations", 2)

        if result.status == "continue_research" and iteration >= max_iterations:
            result = ReflectionResult(
                status="write",
                summary=(
                    "The research iteration budget is exhausted; write with explicit limitations."
                ),
            )

        attempted_queries = list(state.get("attempted_queries", []))

        if result.status == "continue_research":
            attempted_queries.extend(query.query for query in result.supplementary_queries)
            iteration += 1

        return {
            "active_agent": "reflect",
            "reflection_result": result,
            "supplementary_queries": result.supplementary_queries,
            "attempted_queries": attempted_queries,
            "iteration": iteration,
            "status": (
                "supplementary_research_required"
                if result.status == "continue_research"
                else "analysis_approved_for_writing"
            ),
        }

    return reflect_node


def select_eight_agent_reflection_path(
    state: ResearchState,
) -> Literal["research_dispatch", "writer"]:
    """Route Reflect either back to both scouts or forward to Writer."""

    if state["reflection_result"].status == "continue_research":
        return "research_dispatch"

    return "writer"


def build_eight_agent_writer_node(
    write_report: WriterOperation,
    review_report: ReportReviewer,
    *,
    max_attempts: int,
) -> Callable[[ResearchState], Awaitable[dict[str, object]]]:
    """Create the final Writer node with bounded citation repair."""

    async def writer_node(state: ResearchState) -> dict[str, object]:
        previous_report: str | None = None
        revision_feedback: ReflectionDecision | None = None
        report = ""
        audit: CitationAudit | None = None
        decision: ReflectionDecision | None = None

        for _ in range(max_attempts):
            report = await write_report(
                query=state["query"],
                plan=state["plan"],
                analysis=state["analysis"],
                sources=state["evidence_sources"],
                scores=state["evidence_scores"],
                previous_report=previous_report,
                revision_feedback=revision_feedback,
            )
            audit, decision = review_report(
                report,
                state["evidence_sources"],
                state["evidence_scores"],
                state.get("is_high_risk_domain", False),
            )

            if decision.status == "approved":
                break

            previous_report = report
            revision_feedback = decision

        assert audit is not None
        assert decision is not None

        return {
            "active_agent": "writer",
            "draft_report": previous_report or report,
            "report": report,
            "answer": report,
            "citation_audit": audit,
            "reflection": decision,
            "reflection_attempts": max_attempts if previous_report else 1,
            "status": (
                "research_report_completed"
                if decision.status == "approved"
                else "research_report_revision_required"
            ),
        }

    return writer_node


# Node names in build_eight_agent_research_graph that correspond to a real
# agent step worth a durable research_agent_steps trace row -- matches the
# agent_role CHECK constraint exactly. Excludes "initialize" (setup only)
# and "research_dispatch" (a no-op routing passthrough).
AGENT_STEP_NODE_NAMES: frozenset[str] = frozenset(
    {
        "intent_router",
        "direct_answer",
        "planner",
        "web_scout",
        "local_scout",
        "evidence_judge",
        "analyst",
        "reflect",
        "writer",
    }
)


def build_eight_agent_research_graph(
    classifier: IntentClassifier,
    create_plan: PlanCreator,
    generate_direct_answer: DirectAnswerGenerator,
    scout_web: WebTaskScout,
    scout_local: LocalTaskScout,
    judge_evidence: EvidenceJudgeOperation,
    analyze: AnalysisOperation,
    reflect: ReflectionOperation,
    write_report: WriterOperation,
    review_report: ReportReviewer,
    *,
    scout_mcp: MCPQueryScout | None = None,
    max_iterations: int = 2,
    max_writer_attempts: int = 2,
    checkpointer: BaseCheckpointSaver[str] | None = None,
) -> ResearchGraph:
    """Build the canonical eight-agent research workflow."""

    if max_iterations < 0:
        raise ValueError("max_iterations must not be negative.")

    if max_writer_attempts < 1:
        raise ValueError("max_writer_attempts must be at least 1.")

    async def planner_node(state: ResearchState) -> dict[str, object]:
        plan = await create_plan(state["query"])

        return {
            "active_agent": "planner",
            "plan": plan,
            "attempted_queries": [task.search_query for task in plan.tasks],
            "iteration": 0,
            "max_iterations": max_iterations,
            "status": "research_plan_ready",
        }

    graph_builder = StateGraph(ResearchState)
    graph_builder.add_node("initialize", initialize_node)  # type: ignore[call-overload]
    graph_builder.add_node("intent_router", build_route_node(classifier))  # type: ignore[call-overload]
    graph_builder.add_node(  # type: ignore[call-overload]
        "direct_answer",
        build_direct_answer_node(generate_direct_answer),
    )
    graph_builder.add_node("planner", planner_node)
    graph_builder.add_node(
        "web_scout",
        build_eight_agent_web_scout_node(scout_web, scout_mcp),  # type: ignore[arg-type]
    )
    graph_builder.add_node(
        "local_scout",
        build_eight_agent_local_scout_node(scout_local),  # type: ignore[arg-type]
    )
    graph_builder.add_node(
        "evidence_judge",
        build_eight_agent_evidence_judge_node(judge_evidence),  # type: ignore[arg-type]
    )
    graph_builder.add_node(
        "analyst",
        build_eight_agent_analyst_node(analyze),  # type: ignore[arg-type]
    )
    graph_builder.add_node(
        "reflect",
        build_eight_agent_reflect_node(reflect),  # type: ignore[arg-type]
    )
    graph_builder.add_node("research_dispatch", lambda _: {})
    graph_builder.add_node(
        "writer",
        build_eight_agent_writer_node(
            write_report,
            review_report,
            max_attempts=max_writer_attempts,
        ),  # type: ignore[arg-type]
    )

    graph_builder.add_edge(START, "initialize")
    graph_builder.add_edge("initialize", "intent_router")
    graph_builder.add_conditional_edges(
        "intent_router",
        select_route,
        {
            "direct_answer": "direct_answer",
            "planner": "planner",
        },
    )
    graph_builder.add_edge("direct_answer", END)
    graph_builder.add_edge("planner", "web_scout")
    graph_builder.add_edge("planner", "local_scout")
    graph_builder.add_edge(
        ["web_scout", "local_scout"],
        "evidence_judge",
    )
    graph_builder.add_edge("evidence_judge", "analyst")
    graph_builder.add_edge("analyst", "reflect")
    graph_builder.add_conditional_edges(
        "reflect",
        select_eight_agent_reflection_path,
        {
            "research_dispatch": "research_dispatch",
            "writer": "writer",
        },
    )
    graph_builder.add_edge("research_dispatch", "web_scout")
    graph_builder.add_edge("research_dispatch", "local_scout")
    graph_builder.add_edge("writer", END)

    return graph_builder.compile(checkpointer=checkpointer)


def build_research_graph_for_client(
    llm_client: LLMClient,
    *,
    local_scout: LocalScoutAgent | None = None,
    mcp_scout: MCPReferenceScout | None = None,
    checkpointer: BaseCheckpointSaver[str] | None = None,
) -> ResearchGraph:
    """Build the production graph around one supplied LLM client."""

    tavily_client = TavilySearchClient()

    intent_router = IntentRouter(llm_client)
    direct_answer_agent = DirectAnswerAgent(llm_client)
    planner = PlannerAgent(llm_client)
    search_executor = SearchExecutor(
        tavily_client,
        circuit_breaker=CircuitBreaker(),
        retryable_errors=(*DEFAULT_RETRYABLE_ERRORS, TavilyTimeoutError),
    )
    web_scout = WebScoutAgent(search_executor)
    evidence_scorer = EvidenceScorer()
    evidence_judge = EvidenceJudgeAgent(evidence_scorer, llm_client)
    analyst = AnalystAgent(llm_client)
    citation_validator = CitationValidator()
    reflection = ReflectionAgent(llm_client)
    writer = WriterAgent(llm_client)

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
        is_high_risk_domain: bool,
    ) -> tuple[CitationAudit, ReflectionDecision]:
        audit = citation_validator.validate(
            report=report,
            sources=sources,
        )

        return audit, reflection.review(
            citation_audit=audit,
            evidence_scores=scores,
            is_high_risk_domain=is_high_risk_domain,
        )

    if local_scout is not None:
        return build_eight_agent_research_graph(
            intent_router.classify,
            planner.create_plan,
            direct_answer_agent.answer,
            web_scout.scout,
            local_scout.scout_tasks,
            evidence_judge.judge,
            analyst.analyze,
            reflection.reflect,
            writer.write_report,
            review_report,
            scout_mcp=mcp_scout.scout if mcp_scout is not None else None,
            checkpointer=checkpointer,
        )

    return build_research_graph(
        intent_router.classify,
        planner.create_plan,
        direct_answer_agent.answer,
        search_executor.execute,
        scout_private_knowledge=(local_scout.scout if local_scout is not None else None),
        analyze_evidence=analyze_evidence,
        generate_report=generate_report,
        review_report=review_report,
        checkpointer=checkpointer,
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
