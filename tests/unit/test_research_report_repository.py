from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ResearchReport, ResearchSource
from app.db.repositories import ResearchReportRepository
from app.schemas.evidence import (
    CitationAudit,
    EvidenceScore,
    EvidenceSource,
    ReflectionDecision,
)
from app.workflow.state import ResearchState


def create_report_state() -> ResearchState:
    source = EvidenceSource(
        source_id="WEB-0123456789ABCDEF",
        origin="web",
        title="HTTP semantics",
        locator="https://example.com/http",
        content="HTTP evidence.",
        provider="fixture",
    )
    score = EvidenceScore(
        source_id=source.source_id,
        relevance=0.9,
        content_quality=0.8,
        traceability=1,
        overall=0.88,
    )

    return {
        "query": "Explain HTTP semantics.",
        "status": "research_report_completed",
        "report": f"HTTP report. [{source.source_id}]",
        "evidence_sources": [source],
        "evidence_scores": [score],
        "citation_audit": CitationAudit(
            valid=True,
            cited_source_ids=[source.source_id],
            unknown_source_ids=[],
            uncited_claims=[],
            coverage_ratio=1,
        ),
        "reflection": ReflectionDecision(
            status="approved",
            reasons=[],
            evidence_count=1,
            average_evidence_score=0.88,
        ),
        "reflection_attempts": 2,
    }


@pytest.mark.anyio
async def test_repository_persists_report_and_scored_sources_without_commit() -> None:
    session_mock = AsyncMock(spec=AsyncSession)
    added: list[object] = []
    session_mock.add = Mock(side_effect=added.append)

    async def assign_report_identity() -> None:
        for entity in added:
            if isinstance(entity, ResearchReport) and entity.id is None:
                entity.id = uuid4()

    session_mock.flush.side_effect = assign_report_identity
    repository = ResearchReportRepository(cast(AsyncSession, session_mock))
    tenant_id = uuid4()
    research_run_id = uuid4()

    report = await repository.create_from_state(
        tenant_id=tenant_id,
        research_run_id=research_run_id,
        state=create_report_state(),
    )

    assert report is not None
    assert report.tenant_id == tenant_id
    assert report.research_run_id == research_run_id
    assert report.citation_valid is True
    assert report.reflection_status == "approved"
    assert report.reflection_attempts == 2
    assert report.human_review_required is False
    assert report.human_review_reason is None
    assert len(added) == 2

    source = added[1]
    assert isinstance(source, ResearchSource)
    assert source.report_id == report.id
    assert source.source_id == "WEB-0123456789ABCDEF"
    assert source.overall_score == 0.88
    assert source.cited is True
    assert session_mock.flush.await_count == 2


@pytest.mark.anyio
async def test_repository_persists_a_high_risk_reports_human_review_flag() -> None:
    session_mock = AsyncMock(spec=AsyncSession)
    added: list[object] = []
    session_mock.add = Mock(side_effect=added.append)

    async def assign_report_identity() -> None:
        for entity in added:
            if isinstance(entity, ResearchReport) and entity.id is None:
                entity.id = uuid4()

    session_mock.flush.side_effect = assign_report_identity
    repository = ResearchReportRepository(cast(AsyncSession, session_mock))

    state = create_report_state()
    state["reflection"] = ReflectionDecision(
        status="approved",
        reasons=[],
        evidence_count=1,
        average_evidence_score=0.88,
        human_review_required=True,
        human_review_reason="This request touches the medical domain.",
    )

    report = await repository.create_from_state(
        tenant_id=uuid4(),
        research_run_id=uuid4(),
        state=state,
    )

    assert report is not None
    assert report.human_review_required is True
    assert report.human_review_reason == "This request touches the medical domain."
    session_mock.commit.assert_not_awaited()


@pytest.mark.anyio
async def test_repository_skips_direct_answers_without_report() -> None:
    session_mock = AsyncMock(spec=AsyncSession)
    repository = ResearchReportRepository(cast(AsyncSession, session_mock))

    result = await repository.create_from_state(
        tenant_id=uuid4(),
        research_run_id=uuid4(),
        state={
            "query": "Explain epoll.",
            "status": "direct_answer_completed",
            "answer": "epoll monitors file descriptors.",
        },
    )

    assert result is None
    session_mock.add.assert_not_called()
    session_mock.flush.assert_not_awaited()


@pytest.mark.anyio
async def test_repository_rejects_evidence_without_score() -> None:
    session_mock = AsyncMock(spec=AsyncSession)
    added: list[object] = []
    session_mock.add = Mock(side_effect=added.append)

    async def assign_report_identity() -> None:
        for entity in added:
            if isinstance(entity, ResearchReport) and entity.id is None:
                entity.id = uuid4()

    session_mock.flush.side_effect = assign_report_identity
    repository = ResearchReportRepository(cast(AsyncSession, session_mock))
    state = create_report_state()
    state["evidence_scores"] = []

    with pytest.raises(ValueError, match="missing a quality score"):
        await repository.create_from_state(
            tenant_id=uuid4(),
            research_run_id=uuid4(),
            state=state,
        )
