import asyncio
from collections.abc import Sequence
from uuid import UUID, uuid4

import pytest

from app.agents.evidence_judge import EvidenceJudgeAgent, EvidenceJudgeResult
from app.agents.local_scout import LocalScoutResult
from app.agents.reflection import ReflectionAgent
from app.agents.web_scout import WebScoutResult
from app.schemas.evidence import (
    CitationAudit,
    EvidenceScore,
    EvidenceSource,
    ReflectionDecision,
)
from app.schemas.intent import IntentDecision
from app.schemas.planner import ReportSection, ResearchPlan, ResearchTask
from app.schemas.source import PrivateSource, WebSource
from app.schemas.workflow import (
    EvidenceConflict,
    EvidenceGap,
    ReflectionResult,
    ResearchAnalysis,
    ResearchFinding,
    SupplementaryResearchQuery,
)
from app.services.evidence import CitationValidator, EvidenceScorer
from app.workflow.graph import build_eight_agent_research_graph


def create_plan() -> ResearchPlan:
    return ResearchPlan(
        goal="Evaluate queue reliability.",
        sub_questions=["What is delivered?", "How are failures recovered?"],
        tasks=[
            ResearchTask(
                title="Delivery model",
                search_query="queue delivery model",
                rationale="Determine the delivery guarantee.",
            ),
            ResearchTask(
                title="Failure recovery",
                search_query="queue failure recovery",
                rationale="Determine the recovery mechanism.",
            ),
        ],
        report_outline=[
            ReportSection(title="Conclusion", purpose="State the result."),
            ReportSection(title="Evidence", purpose="Explain the sources."),
            ReportSection(title="Risks", purpose="State residual uncertainty."),
        ],
    )


def web_source(source_id: str = "WEB-0123456789ABCDEF") -> WebSource:
    return WebSource(
        source_id=source_id,
        title="Queue delivery documentation",
        url="https://example.com/queue",
        content="The queue uses at-least-once delivery with retries.",
        provider="fixture",
    )


def private_source(
    source_id: str = "PRIVATE-FEDCBA9876543210",
) -> PrivateSource:
    suffix = source_id.removeprefix("PRIVATE-")

    return PrivateSource(
        source_id=source_id,
        document_id=f"DOC-{suffix}",
        chunk_id=f"CHK-{suffix}",
        filename="queue.md",
        media_type="text/markdown",
        content="Internal workers retry after a visibility timeout.",
        score=0.92,
    )


async def deep_route(_: str) -> IntentDecision:
    return IntentDecision(route="deep_research", reason="Evidence is required.")


async def direct_route(_: str) -> IntentDecision:
    return IntentDecision(route="direct", reason="Stable knowledge is sufficient.")


async def plan(_: str) -> ResearchPlan:
    return create_plan()


async def direct_answer(query: str) -> str:
    return f"Direct: {query}"


def approved_review(
    report: str,
    sources: list[EvidenceSource],
    scores: list[EvidenceScore],
    is_high_risk_domain: bool = False,
) -> tuple[CitationAudit, ReflectionDecision]:
    audit = CitationValidator().validate(report=report, sources=sources)
    decision = ReflectionAgent().review(
        citation_audit=audit,
        evidence_scores=scores,
        is_high_risk_domain=is_high_risk_domain,
    )

    return audit, decision


@pytest.mark.anyio
async def test_eight_agent_graph_runs_parallel_scouts_and_writes_report() -> None:
    web_started = asyncio.Event()
    local_started = asyncio.Event()
    events: list[str] = []
    judge = EvidenceJudgeAgent(EvidenceScorer())

    async def scout_web(tasks: Sequence[ResearchTask]) -> WebScoutResult:
        events.append("web_scout")
        assert len(tasks) == 2
        web_started.set()
        await asyncio.wait_for(local_started.wait(), timeout=1)
        return WebScoutResult(outcomes=[], sources=[web_source()])

    async def scout_local(
        tasks: Sequence[ResearchTask],
        tenant_id: UUID,
        *,
        document_ids: Sequence[str] | None = None,
    ) -> LocalScoutResult:
        events.append("local_scout")
        assert len(tasks) == 2
        assert tenant_id == expected_tenant_id
        local_started.set()
        await asyncio.wait_for(web_started.wait(), timeout=1)
        return LocalScoutResult(sources=[private_source()], errors=[])

    async def judge_evidence(
        *,
        query: str,
        web_sources: Sequence[WebSource],
        private_sources: Sequence[PrivateSource],
        additional_sources: Sequence[EvidenceSource] = (),
    ) -> EvidenceJudgeResult:
        events.append("evidence_judge")
        assert web_started.is_set() and local_started.is_set()
        return await judge.judge(
            query=query,
            web_sources=web_sources,
            private_sources=private_sources,
            additional_sources=additional_sources,
        )

    async def analyze(
        *,
        query: str,
        sources: Sequence[EvidenceSource],
        scores: Sequence[EvidenceScore],
        conflicts: Sequence[EvidenceConflict] = (),
    ) -> ResearchAnalysis:
        events.append("analyst")
        assert query and len(scores) == 2
        return ResearchAnalysis(
            summary="The queue uses at-least-once delivery.",
            findings=[
                ResearchFinding(
                    claim="Duplicate delivery is possible.",
                    confidence="high",
                    source_ids=[source.source_id for source in sources],
                )
            ],
            needs_more_research=False,
        )

    async def reflect(
        *,
        analysis: ResearchAnalysis,
        evidence_gaps: Sequence[EvidenceGap],
        attempted_queries: Sequence[str],
    ) -> ReflectionResult:
        events.append("reflect")
        assert analysis.findings and not evidence_gaps and attempted_queries
        return ReflectionResult(
            status="write",
            summary="Evidence is sufficient.",
        )

    async def write_report(
        *,
        query: str,
        plan: ResearchPlan,
        analysis: ResearchAnalysis,
        sources: Sequence[EvidenceSource],
        scores: Sequence[EvidenceScore],
        previous_report: str | None = None,
        revision_feedback: ReflectionDecision | None = None,
    ) -> str:
        events.append("writer")
        assert query and plan.goal and analysis.findings and scores
        assert previous_report is None and revision_feedback is None
        return (
            f"The queue uses at-least-once delivery. [{sources[0].source_id}]\n\n"
            f"Workers retry timed-out messages. [{sources[1].source_id}]"
        )

    expected_tenant_id = uuid4()
    graph = build_eight_agent_research_graph(
        deep_route,
        plan,
        direct_answer,
        scout_web,
        scout_local,
        judge_evidence,
        analyze,
        reflect,
        write_report,
        approved_review,
    )

    result = await graph.ainvoke(
        {
            "query": "Evaluate queue reliability.",
            "tenant_id": expected_tenant_id,
        }
    )

    assert set(events[:2]) == {"web_scout", "local_scout"}
    assert events[2:] == ["evidence_judge", "analyst", "reflect", "writer"]
    assert result["active_agent"] == "writer"
    assert result["status"] == "research_report_completed"
    assert result["citation_audit"].valid is True
    assert [source.origin for source in result["evidence_sources"]] == [
        "web",
        "private",
    ]


@pytest.mark.anyio
async def test_eight_agent_graph_reflects_into_one_follow_up_round() -> None:
    web_queries: list[list[str]] = []
    local_queries: list[list[str]] = []
    analysis_calls = 0
    judge = EvidenceJudgeAgent(EvidenceScorer())

    async def scout_web(tasks: Sequence[ResearchTask]) -> WebScoutResult:
        web_queries.append([task.search_query for task in tasks])
        source = web_source() if len(web_queries) == 1 else web_source("WEB-AAAAAAAAAAAAAAAA")
        return WebScoutResult(outcomes=[], sources=[source])

    async def scout_local(
        tasks: Sequence[ResearchTask],
        _: UUID,
        *,
        document_ids: Sequence[str] | None = None,
    ) -> LocalScoutResult:
        local_queries.append([task.search_query for task in tasks])
        return LocalScoutResult(sources=[private_source()], errors=[])

    async def analyze(
        *,
        query: str,
        sources: Sequence[EvidenceSource],
        scores: Sequence[EvidenceScore],
        conflicts: Sequence[EvidenceConflict] = (),
    ) -> ResearchAnalysis:
        nonlocal analysis_calls
        analysis_calls += 1
        assert query and sources and scores

        if analysis_calls == 1:
            return ResearchAnalysis(
                summary="Recovery evidence is incomplete.",
                needs_more_research=True,
                gaps=[
                    EvidenceGap(
                        topic="dead-letter queue handling",
                        reason="Terminal failures are not covered.",
                        source_preference="web",
                    )
                ],
            )

        return ResearchAnalysis(
            summary="Recovery evidence is now sufficient.",
            findings=[
                ResearchFinding(
                    claim="Terminal failures are sent to a dead-letter queue.",
                    confidence="medium",
                    source_ids=["WEB-AAAAAAAAAAAAAAAA"],
                )
            ],
            needs_more_research=False,
        )

    reflect_calls = 0

    async def reflect(
        *,
        analysis: ResearchAnalysis,
        evidence_gaps: Sequence[EvidenceGap],
        attempted_queries: Sequence[str],
    ) -> ReflectionResult:
        nonlocal reflect_calls
        reflect_calls += 1

        if reflect_calls == 1:
            assert analysis.needs_more_research and attempted_queries
            return ReflectionResult(
                status="continue_research",
                summary="Search for dead-letter handling.",
                supplementary_queries=[
                    SupplementaryResearchQuery(
                        query="dead-letter queue handling",
                        source_preference="web",
                        reason="Resolve terminal failure behavior.",
                    )
                ],
            )

        return ReflectionResult(status="write", summary="Evidence is sufficient.")

    async def write_report(
        *,
        query: str,
        plan: ResearchPlan,
        analysis: ResearchAnalysis,
        sources: Sequence[EvidenceSource],
        scores: Sequence[EvidenceScore],
        previous_report: str | None = None,
        revision_feedback: ReflectionDecision | None = None,
    ) -> str:
        assert query and plan.goal and analysis.findings and scores
        assert previous_report is None and revision_feedback is None
        return f"Terminal failures use a dead-letter queue. [{sources[-1].source_id}]"

    graph = build_eight_agent_research_graph(
        deep_route,
        plan,
        direct_answer,
        scout_web,
        scout_local,
        judge.judge,
        analyze,
        reflect,
        write_report,
        approved_review,
    )
    result = await graph.ainvoke(
        {
            "query": "Evaluate queue reliability.",
            "tenant_id": uuid4(),
        }
    )

    assert analysis_calls == 2
    assert reflect_calls == 2
    assert web_queries[1] == ["dead-letter queue handling"]
    assert local_queries[1] == []
    assert result["iteration"] == 1
    assert result["status"] == "research_report_completed"


@pytest.mark.anyio
async def test_eight_agent_graph_direct_route_skips_research_agents() -> None:
    async def unexpected(*_: object, **__: object) -> object:
        raise AssertionError("Deep-research agent must not run for direct requests.")

    graph = build_eight_agent_research_graph(
        direct_route,
        plan,
        direct_answer,
        unexpected,  # type: ignore[arg-type]
        unexpected,  # type: ignore[arg-type]
        unexpected,  # type: ignore[arg-type]
        unexpected,  # type: ignore[arg-type]
        unexpected,  # type: ignore[arg-type]
        unexpected,  # type: ignore[arg-type]
        approved_review,
    )

    result = await graph.ainvoke(
        {
            "query": "Explain idempotency.",
            "tenant_id": uuid4(),
        }
    )

    assert result["route"] == "direct"
    assert result["answer"] == "Direct: Explain idempotency."
    assert "plan" not in result
