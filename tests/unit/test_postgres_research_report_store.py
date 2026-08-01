from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ResearchReport, ResearchSource
from app.db.repositories import ResearchReportRepository
from app.services.research.reports import PostgresResearchReportStore


class RecordingSessionFactory:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.begin_calls = 0

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[AsyncSession]:
        self.begin_calls += 1
        yield self.session


@pytest.mark.anyio
async def test_report_store_returns_tenant_scoped_report_and_sources() -> None:
    session = cast(AsyncSession, AsyncMock(spec=AsyncSession))
    session_factory = RecordingSessionFactory(session)
    repository_mock = AsyncMock(spec=ResearchReportRepository)
    repository = cast(ResearchReportRepository, repository_mock)
    tenant_id = uuid4()
    research_run_id = uuid4()
    report_id = uuid4()
    created_at = datetime.now(UTC)
    repository_mock.get_for_run.return_value = ResearchReport(
        id=report_id,
        tenant_id=tenant_id,
        research_run_id=research_run_id,
        content="Evidence-backed report.",
        workflow_status="research_report_completed",
        citation_valid=True,
        citation_coverage=1,
        reflection_status="approved",
        reflection_reasons=[],
        reflection_attempts=1,
        created_at=created_at,
    )
    repository_mock.list_sources_for_run.return_value = [
        ResearchSource(
            id=uuid4(),
            report_id=report_id,
            tenant_id=tenant_id,
            research_run_id=research_run_id,
            source_id="WEB-0123456789ABCDEF",
            origin="web",
            title="HTTP specification",
            locator="https://example.com/http",
            content="HTTP evidence.",
            provider="fixture",
            relevance=0.9,
            content_quality=0.8,
            traceability=1,
            overall_score=0.88,
            cited=True,
        )
    ]

    store = PostgresResearchReportStore(
        session_factory,
        lambda _: repository,
    )

    result = await store.get(
        tenant_id=tenant_id,
        research_run_id=research_run_id,
    )

    assert result is not None
    assert result.report_id == report_id
    assert result.research_run_id == research_run_id
    assert result.reflection_status == "approved"
    assert result.reflection_attempts == 1
    assert result.sources[0].source_id == "WEB-0123456789ABCDEF"
    assert result.sources[0].cited is True
    assert session_factory.begin_calls == 1
    repository_mock.get_for_run.assert_awaited_once_with(
        tenant_id=tenant_id,
        research_run_id=research_run_id,
    )


@pytest.mark.anyio
async def test_report_store_returns_none_without_cross_tenant_fallback() -> None:
    session = cast(AsyncSession, AsyncMock(spec=AsyncSession))
    session_factory = RecordingSessionFactory(session)
    repository_mock = AsyncMock(spec=ResearchReportRepository)
    repository_mock.get_for_run.return_value = None
    repository = cast(ResearchReportRepository, repository_mock)
    tenant_id = uuid4()
    research_run_id = uuid4()
    store = PostgresResearchReportStore(
        session_factory,
        lambda _: repository,
    )

    result = await store.get(
        tenant_id=tenant_id,
        research_run_id=research_run_id,
    )

    assert result is None
    repository_mock.list_sources_for_run.assert_not_awaited()
