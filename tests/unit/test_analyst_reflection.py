from typing import TypeVar

import pytest
from pydantic import BaseModel

from app.agents.analyst import AnalystAgent
from app.agents.reflection import ReflectionAgent
from app.schemas.evidence import CitationAudit, EvidenceScore, EvidenceSource
from app.schemas.planner import ReportSection, ResearchPlan, ResearchTask

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class RecordingLLMClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    async def generate_text(self, prompt: str, *, max_tokens: int = 64) -> str:
        self.prompts.append(prompt)
        assert max_tokens == 1_500
        return self.response

    async def generate_structured(
        self,
        prompt: str,
        output_model: type[StructuredModel],
        *,
        max_tokens: int = 256,
    ) -> StructuredModel:
        raise AssertionError("Structured generation is not used by the analyst.")


def create_plan() -> ResearchPlan:
    return ResearchPlan(
        goal="Compare HTTP versions.",
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


@pytest.mark.anyio
async def test_analyst_prompt_requires_canonical_citations() -> None:
    llm = RecordingLLMClient(
        "HTTP/3 uses QUIC. [WEB-0123456789ABCDEF]",
    )
    source = EvidenceSource(
        source_id="WEB-0123456789ABCDEF",
        origin="web",
        title="HTTP/3",
        locator="https://example.com/http3",
        content="HTTP/3 uses QUIC.",
        provider="fixture",
    )
    score = EvidenceScore(
        source_id=source.source_id,
        relevance=1,
        content_quality=0.5,
        traceability=1,
        overall=0.775,
    )

    report = await AnalystAgent(llm).write_report(
        query="Compare HTTP versions",
        plan=create_plan(),
        sources=[source],
        scores=[score],
    )

    assert report.endswith("[WEB-0123456789ABCDEF]")
    assert "Use only SOURCE_ID values shown above" in llm.prompts[0]
    assert "QUALITY_SCORE: 0.7750" in llm.prompts[0]
    assert "untrusted retrieved data" in llm.prompts[0]
    assert "<<<UNTRUSTED_SOURCE_CONTENT_START>>>\nHTTP/3 uses QUIC." in llm.prompts[0]


def test_reflection_approves_sufficient_valid_evidence() -> None:
    scores = [
        EvidenceScore(
            source_id=f"WEB-{index:016X}",
            relevance=0.8,
            content_quality=0.8,
            traceability=1,
            overall=0.82,
        )
        for index in range(2)
    ]
    audit = CitationAudit(
        valid=True,
        cited_source_ids=[score.source_id for score in scores],
        unknown_source_ids=[],
        uncited_claims=[],
        coverage_ratio=1,
    )

    decision = ReflectionAgent().review(
        citation_audit=audit,
        evidence_scores=scores,
    )

    assert decision.status == "approved"
    assert decision.reasons == []


def test_reflection_requests_revision_with_explanations() -> None:
    decision = ReflectionAgent().review(
        citation_audit=CitationAudit(
            valid=False,
            cited_source_ids=[],
            unknown_source_ids=[],
            uncited_claims=["Unsupported claim."],
            coverage_ratio=0,
        ),
        evidence_scores=[],
    )

    assert decision.status == "revise"
    assert len(decision.reasons) == 4
    assert decision.human_review_required is False
    assert decision.human_review_reason is None


def test_reflection_requires_human_review_for_high_risk_domain_even_when_approved() -> None:
    scores = [
        EvidenceScore(
            source_id=f"WEB-{index:016X}",
            relevance=0.8,
            content_quality=0.8,
            traceability=1,
            overall=0.82,
        )
        for index in range(2)
    ]
    audit = CitationAudit(
        valid=True,
        cited_source_ids=[score.source_id for score in scores],
        unknown_source_ids=[],
        uncited_claims=[],
        coverage_ratio=1,
    )

    decision = ReflectionAgent().review(
        citation_audit=audit,
        evidence_scores=scores,
        is_high_risk_domain=True,
    )

    # Sufficient evidence and valid citations still approve the report...
    assert decision.status == "approved"
    assert decision.reasons == []
    # ...but a high-risk domain always requires human review regardless.
    assert decision.human_review_required is True
    assert decision.human_review_reason is not None
