from typing import TypeVar, cast

import pytest
from pydantic import BaseModel

from app.agents.analyst import AnalystAgent
from app.agents.evidence_judge import EvidenceJudgeAgent
from app.agents.reflection import ReflectionAgent
from app.agents.web_scout import WebScoutAgent
from app.agents.writer import WriterAgent
from app.schemas.evidence import EvidenceScore, EvidenceSource
from app.schemas.planner import ReportSection, ResearchPlan, ResearchTask
from app.schemas.source import PrivateSource, WebSource
from app.schemas.workflow import (
    EvidenceConflict,
    EvidenceGap,
    EvidenceJudgment,
    ReflectionResult,
    ResearchAnalysis,
    ResearchFinding,
    SupplementaryResearchQuery,
)
from app.services.evidence import EvidenceScorer
from app.services.search.base import SearchResult
from app.services.search.executor import SearchExecutor

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class RecordingLLMClient:
    def __init__(
        self,
        *,
        structured: dict[type[BaseModel], BaseModel] | None = None,
        text: str = "",
    ) -> None:
        self.structured = structured or {}
        self.text = text
        self.prompts: list[str] = []

    async def generate_text(
        self,
        prompt: str,
        *,
        max_tokens: int = 64,
    ) -> str:
        self.prompts.append(prompt)
        assert max_tokens == 4_500
        return self.text

    async def generate_structured(
        self,
        prompt: str,
        output_model: type[StructuredModel],
        *,
        max_tokens: int = 256,
    ) -> StructuredModel:
        self.prompts.append(prompt)
        assert max_tokens in {2_000, 2_500, 8_000}
        return cast(StructuredModel, self.structured[output_model])


class RecordingSearchClient:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
    ) -> list[SearchResult]:
        self.queries.append(query)

        return [
            SearchResult(
                title=f"Source for {query}",
                url=f"https://example.com/{len(self.queries)}",
                content=f"Evidence for {query}.",
                source="fixture",
            )
        ][:max_results]


def create_tasks() -> list[ResearchTask]:
    return [
        ResearchTask(
            title="Queue delivery",
            search_query="queue delivery guarantee",
            rationale="Determine the delivery model.",
        ),
        ResearchTask(
            title="Queue recovery",
            search_query="queue worker recovery",
            rationale="Determine the recovery behavior.",
        ),
    ]


def create_plan() -> ResearchPlan:
    return ResearchPlan(
        goal="Evaluate queue reliability.",
        sub_questions=["What is delivered?", "How are failures recovered?"],
        tasks=create_tasks(),
        report_outline=[
            ReportSection(title="Conclusion", purpose="State the answer."),
            ReportSection(title="Evidence", purpose="Explain supporting evidence."),
            ReportSection(title="Risks", purpose="State remaining uncertainty."),
        ],
    )


def create_web_source() -> WebSource:
    return WebSource(
        source_id="WEB-0123456789ABCDEF",
        title="Queue delivery documentation",
        url="https://example.com/queue",
        content="The queue uses at-least-once delivery with worker retries.",
        provider="fixture",
    )


def create_private_source() -> PrivateSource:
    return PrivateSource(
        source_id="PRIVATE-FEDCBA9876543210",
        document_id="DOC-FEDCBA9876543210",
        chunk_id="CHK-FEDCBA9876543210",
        filename="queue.md",
        media_type="text/markdown",
        content="Internal workers retry messages after a visibility timeout.",
        score=0.92,
    )


@pytest.mark.anyio
async def test_web_scout_executes_explicit_task_batch() -> None:
    search_client = RecordingSearchClient()
    scout = WebScoutAgent(SearchExecutor(search_client))

    result = await scout.scout(create_tasks())

    assert search_client.queries == [
        "queue delivery guarantee",
        "queue worker recovery",
    ]
    assert len(result.outcomes) == 2
    assert len(result.sources) == 2


@pytest.mark.anyio
async def test_evidence_judge_merges_web_and_private_sources() -> None:
    conflict = EvidenceConflict(
        claim="The queue provides exactly-once delivery.",
        source_ids=[
            "WEB-0123456789ABCDEF",
            "PRIVATE-FEDCBA9876543210",
        ],
        explanation="The sources describe different delivery guarantees.",
    )
    judgment = EvidenceJudgment(conflicts=[conflict])
    llm = RecordingLLMClient(structured={EvidenceJudgment: judgment})
    judge = EvidenceJudgeAgent(EvidenceScorer(), llm)

    result = await judge.judge(
        query="Evaluate queue delivery guarantees",
        web_sources=[create_web_source()],
        private_sources=[create_private_source()],
    )

    assert [source.origin for source in result.sources] == ["web", "private"]
    assert len(result.scores) == 2
    assert result.judgment == judgment
    assert "Do not invent sources" in llm.prompts[0]


@pytest.mark.anyio
async def test_evidence_judge_falls_back_when_llm_invents_source() -> None:
    invalid_judgment = EvidenceJudgment(
        conflicts=[
            EvidenceConflict(
                claim="Invented conflict",
                source_ids=[
                    "WEB-0123456789ABCDEF",
                    "WEB-FFFFFFFFFFFFFFFF",
                ],
                explanation="One source does not exist.",
            )
        ]
    )
    llm = RecordingLLMClient(structured={EvidenceJudgment: invalid_judgment})
    judge = EvidenceJudgeAgent(EvidenceScorer(), llm)

    result = await judge.judge(
        query="Evaluate queue delivery guarantees",
        web_sources=[create_web_source()],
        private_sources=[],
    )

    assert result.judgment.conflicts == []
    assert result.judgment.gaps[0].topic == "Independent source coverage"


@pytest.mark.anyio
async def test_analyst_returns_source_bound_structured_findings() -> None:
    source = EvidenceSource(
        source_id="WEB-0123456789ABCDEF",
        origin="web",
        title="Queue delivery",
        locator="https://example.com/queue",
        content="The queue uses at-least-once delivery.",
        provider="fixture",
    )
    analysis = ResearchAnalysis(
        summary="The queue uses at-least-once delivery.",
        findings=[
            ResearchFinding(
                claim="Messages may be delivered more than once.",
                confidence="high",
                source_ids=[source.source_id],
            )
        ],
        needs_more_research=False,
    )
    llm = RecordingLLMClient(structured={ResearchAnalysis: analysis})

    result = await AnalystAgent(llm).analyze(
        query="Evaluate queue delivery",
        sources=[source],
        scores=[
            EvidenceScore(
                source_id=source.source_id,
                relevance=1,
                content_quality=0.5,
                traceability=1,
                overall=0.775,
            )
        ],
    )

    assert result == analysis
    assert "untrusted retrieved data" in llm.prompts[0]
    assert "<<<UNTRUSTED_SOURCE_CONTENT_START>>>" in llm.prompts[0]


@pytest.mark.anyio
async def test_analyst_falls_back_when_llm_invents_a_source_id() -> None:
    source = EvidenceSource(
        source_id="WEB-0123456789ABCDEF",
        origin="web",
        title="Queue delivery",
        locator="https://example.com/queue",
        content="The queue uses at-least-once delivery.",
        provider="fixture",
    )
    invalid_analysis = ResearchAnalysis(
        summary="Invented finding.",
        findings=[
            ResearchFinding(
                claim="Invented claim.",
                confidence="high",
                source_ids=["WEB-FFFFFFFFFFFFFFFF"],
            )
        ],
        needs_more_research=False,
    )
    llm = RecordingLLMClient(structured={ResearchAnalysis: invalid_analysis})

    result = await AnalystAgent(llm).analyze(
        query="Evaluate queue delivery",
        sources=[source],
        scores=[
            EvidenceScore(
                source_id=source.source_id,
                relevance=1,
                content_quality=0.5,
                traceability=1,
                overall=0.775,
            )
        ],
    )

    assert result.findings == []
    assert result.needs_more_research is False


@pytest.mark.anyio
async def test_analyst_caps_evidence_to_the_highest_scored_sources() -> None:
    high = EvidenceSource(
        source_id="WEB-0000000000000001",
        origin="web",
        title="On-topic queue delivery guide",
        locator="https://example.com/queue",
        content="The queue uses at-least-once delivery.",
        provider="fixture",
    )
    low = EvidenceSource(
        source_id="WEB-0000000000000002",
        origin="web",
        title="Unrelated dictionary definition",
        locator="https://example.com/definition",
        content="A definition of an unrelated word.",
        provider="fixture",
    )
    analysis = ResearchAnalysis(
        summary="The queue uses at-least-once delivery.",
        findings=[],
        needs_more_research=False,
    )
    llm = RecordingLLMClient(structured={ResearchAnalysis: analysis})

    await AnalystAgent(llm, max_evidence_sources=1).analyze(
        query="Evaluate queue delivery",
        sources=[low, high],
        scores=[
            EvidenceScore(
                source_id=high.source_id,
                relevance=1,
                content_quality=1,
                traceability=1,
                overall=0.9,
            ),
            EvidenceScore(
                source_id=low.source_id,
                relevance=0.1,
                content_quality=1,
                traceability=1,
                overall=0.2,
            ),
        ],
    )

    assert high.source_id in llm.prompts[0]
    assert low.source_id not in llm.prompts[0]


@pytest.mark.anyio
async def test_reflect_removes_attempted_queries() -> None:
    repeated = SupplementaryResearchQuery(
        query="queue worker recovery",
        source_preference="hybrid",
        reason="Fill the recovery gap.",
    )
    fresh = SupplementaryResearchQuery(
        query="queue dead-letter handling",
        source_preference="private",
        reason="Find the terminal failure path.",
    )
    reflection = ReflectionResult(
        status="continue_research",
        summary="More recovery evidence is required.",
        supplementary_queries=[repeated, fresh],
    )
    llm = RecordingLLMClient(structured={ReflectionResult: reflection})
    agent = ReflectionAgent(llm)

    result = await agent.reflect(
        analysis=ResearchAnalysis(
            summary="Recovery remains unclear.",
            needs_more_research=True,
        ),
        evidence_gaps=[
            EvidenceGap(
                topic="Recovery behavior",
                reason="No terminal failure evidence was found.",
            )
        ],
        attempted_queries=["queue worker recovery"],
    )

    assert result.status == "continue_research"
    assert result.supplementary_queries == [fresh]


@pytest.mark.anyio
async def test_writer_uses_approved_analysis_and_source_ids() -> None:
    source = EvidenceSource(
        source_id="WEB-0123456789ABCDEF",
        origin="web",
        title="Queue delivery",
        locator="https://example.com/queue",
        content="The queue uses at-least-once delivery.",
        provider="fixture",
    )
    analysis = ResearchAnalysis(
        summary="The queue uses at-least-once delivery.",
        findings=[
            ResearchFinding(
                claim="Duplicate delivery is possible.",
                confidence="high",
                source_ids=[source.source_id],
            )
        ],
        needs_more_research=False,
    )
    llm = RecordingLLMClient(text="Duplicate delivery is possible. [WEB-0123456789ABCDEF]")

    report = await WriterAgent(llm).write_report(
        query="Evaluate queue delivery",
        plan=create_plan(),
        analysis=analysis,
        sources=[source],
        scores=[
            EvidenceScore(
                source_id=source.source_id,
                relevance=1,
                content_quality=0.5,
                traceability=1,
                overall=0.775,
            )
        ],
    )

    assert report.endswith("[WEB-0123456789ABCDEF]")
    assert "Approved findings" in llm.prompts[0]
    assert "untrusted retrieved data" in llm.prompts[0]
    assert "<<<UNTRUSTED_SOURCE_CONTENT_START>>>" in llm.prompts[0]


@pytest.mark.anyio
async def test_writer_caps_evidence_to_the_highest_scored_sources() -> None:
    high = EvidenceSource(
        source_id="WEB-0000000000000001",
        origin="web",
        title="On-topic queue delivery guide",
        locator="https://example.com/queue",
        content="The queue uses at-least-once delivery.",
        provider="fixture",
    )
    low = EvidenceSource(
        source_id="WEB-0000000000000002",
        origin="web",
        title="Unrelated dictionary definition",
        locator="https://example.com/definition",
        content="A definition of an unrelated word.",
        provider="fixture",
    )
    analysis = ResearchAnalysis(
        summary="The queue uses at-least-once delivery.",
        findings=[],
        needs_more_research=False,
    )
    llm = RecordingLLMClient(text="Duplicate delivery is possible. [WEB-0000000000000001]")

    await WriterAgent(llm, max_evidence_sources=1).write_report(
        query="Evaluate queue delivery",
        plan=create_plan(),
        analysis=analysis,
        sources=[low, high],
        scores=[
            EvidenceScore(
                source_id=high.source_id,
                relevance=1,
                content_quality=1,
                traceability=1,
                overall=0.9,
            ),
            EvidenceScore(
                source_id=low.source_id,
                relevance=0.1,
                content_quality=1,
                traceability=1,
                overall=0.2,
            ),
        ],
    )

    assert high.source_id in llm.prompts[0]
    assert low.source_id not in llm.prompts[0]


@pytest.mark.anyio
async def test_writer_groups_private_evidence_into_its_own_labeled_section() -> None:
    private_source = EvidenceSource(
        source_id="PRIVATE-0000000000000001",
        origin="private",
        title="onboarding-runbook.md",
        locator="DOC-0000000000000001/CHK-0000000000000001",
        content="Week 1: clone the monorepo and run the local stack.",
        provider="private_knowledge",
    )
    web_source = EvidenceSource(
        source_id="WEB-0000000000000001",
        origin="web",
        title="Generic onboarding checklist",
        locator="https://example.com/onboarding",
        content="Generic industry onboarding advice.",
        provider="fixture",
    )
    analysis = ResearchAnalysis(
        summary="Summarize the internal onboarding runbook.",
        findings=[],
        needs_more_research=False,
    )
    llm = RecordingLLMClient(text="Week 1 covers environment setup. [PRIVATE-0000000000000001]")

    await WriterAgent(llm).write_report(
        query="Summarize our internal onboarding runbook",
        plan=create_plan(),
        analysis=analysis,
        sources=[web_source, private_source],
        scores=[
            EvidenceScore(
                source_id=private_source.source_id,
                relevance=0.9,
                content_quality=1,
                traceability=1,
                overall=0.9,
            ),
            EvidenceScore(
                source_id=web_source.source_id,
                relevance=0.5,
                content_quality=1,
                traceability=1,
                overall=0.6,
            ),
        ],
    )

    prompt = llm.prompts[0]
    assert "YOUR ORGANIZATION'S OWN PRIVATE KNOWLEDGE" in prompt
    assert "PUBLIC WEB AND ACADEMIC SOURCES" in prompt
    # The private section must appear before the public section so a
    # position-sensitive model encounters the authoritative evidence first.
    assert prompt.index("PRIVATE KNOWLEDGE") < prompt.index("PUBLIC WEB")
    assert private_source.source_id in prompt
    assert web_source.source_id in prompt


@pytest.mark.anyio
async def test_writer_omits_the_private_section_when_no_private_evidence_exists() -> None:
    web_source = EvidenceSource(
        source_id="WEB-0000000000000001",
        origin="web",
        title="HTTP/3 overview",
        locator="https://example.com/http3",
        content="HTTP/3 uses QUIC.",
        provider="fixture",
    )
    analysis = ResearchAnalysis(
        summary="HTTP/3 uses QUIC.",
        findings=[],
        needs_more_research=False,
    )
    llm = RecordingLLMClient(text="HTTP/3 uses QUIC. [WEB-0000000000000001]")

    await WriterAgent(llm).write_report(
        query="Explain HTTP/3",
        plan=create_plan(),
        analysis=analysis,
        sources=[web_source],
        scores=[
            EvidenceScore(
                source_id=web_source.source_id,
                relevance=0.9,
                content_quality=1,
                traceability=1,
                overall=0.9,
            ),
        ],
    )

    prompt = llm.prompts[0]
    assert "=== YOUR ORGANIZATION'S OWN PRIVATE KNOWLEDGE ===" not in prompt
    assert "=== PUBLIC WEB AND ACADEMIC SOURCES ===" in prompt
