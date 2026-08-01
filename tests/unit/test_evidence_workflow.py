import pytest

from app.schemas.evidence import (
    CitationAudit,
    EvidenceScore,
    EvidenceSource,
    ReflectionDecision,
)
from app.schemas.intent import IntentDecision
from app.schemas.planner import ReportSection, ResearchPlan, ResearchTask
from app.schemas.source import WebSource
from app.services.evidence import EvidenceScorer, normalize_web_sources
from app.services.search.base import SearchResult
from app.services.search.executor import ResearchTaskResult
from app.workflow.graph import build_research_graph


async def classify(_: str) -> IntentDecision:
    return IntentDecision(route="deep_research", reason="Current evidence is required.")


async def create_plan(_: str) -> ResearchPlan:
    return ResearchPlan(
        goal="Compare HTTP/2 and HTTP/3.",
        sub_questions=["How do transports differ?", "What are the tradeoffs?"],
        tasks=[
            ResearchTask(title="HTTP/2", search_query="HTTP/2", rationale="Compare"),
            ResearchTask(title="HTTP/3", search_query="HTTP/3", rationale="Compare"),
        ],
        report_outline=[
            ReportSection(title="Summary", purpose="Summarize evidence"),
            ReportSection(title="Comparison", purpose="Compare transports"),
            ReportSection(title="Conclusion", purpose="State limitations"),
        ],
    )


async def direct_answer(query: str) -> str:
    return query


async def search(plan: ResearchPlan) -> list[ResearchTaskResult]:
    urls = ["https://example.com/http2", "https://example.com/http3"]

    return [
        ResearchTaskResult(
            task=task,
            results=[
                SearchResult(
                    title=task.title,
                    url=url,
                    content=f"{task.title} transport evidence and deployment tradeoffs.",
                    source="fixture",
                )
            ],
        )
        for task, url in zip(plan.tasks, urls, strict=True)
    ]


def analyze(
    query: str,
    web_sources: list[WebSource],
) -> tuple[list[EvidenceSource], list[EvidenceScore]]:
    sources = normalize_web_sources(web_sources)
    return sources, EvidenceScorer().score(query=query, sources=sources)


async def write_report(
    query: str,
    plan: ResearchPlan,
    sources: list[EvidenceSource],
    scores: list[EvidenceScore],
) -> str:
    assert query
    assert plan.goal
    assert len(scores) == 2
    return (
        f"HTTP/2 evidence is available. [{sources[0].source_id}]\n\n"
        f"HTTP/3 evidence is available. [{sources[1].source_id}]"
    )


def review(
    report: str,
    sources: list[EvidenceSource],
    scores: list[EvidenceScore],
) -> tuple[CitationAudit, ReflectionDecision]:
    assert report
    audit = CitationAudit(
        valid=True,
        cited_source_ids=[source.source_id for source in sources],
        unknown_source_ids=[],
        uncited_claims=[],
        coverage_ratio=1,
    )
    decision = ReflectionDecision(
        status="approved",
        reasons=[],
        evidence_count=len(scores),
        average_evidence_score=sum(score.overall for score in scores) / len(scores),
    )
    return audit, decision


@pytest.mark.anyio
async def test_deep_research_runs_evidence_analyst_and_reflection_pipeline() -> None:
    graph = build_research_graph(
        classify,
        create_plan,
        direct_answer,
        search,
        analyze_evidence=analyze,
        generate_report=write_report,
        review_report=review,
    )

    result = await graph.ainvoke({"query": "Compare HTTP/2 and HTTP/3."})

    assert result["status"] == "research_report_completed"
    assert result["answer"] == result["report"]
    assert len(result["evidence_sources"]) == 2
    assert len(result["evidence_scores"]) == 2
    assert result["citation_audit"].valid is True
    assert result["reflection"].status == "approved"
