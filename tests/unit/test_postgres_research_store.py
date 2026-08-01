from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ResearchRun
from app.db.repositories import ResearchReportRepository, ResearchRunRepository
from app.services.research.postgres import (
    PostgresResearchRunStore,
)
from app.workflow.state import ResearchState


class RecordingSessionFactory:
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.session = session
        self.begin_calls = 0

    @asynccontextmanager
    async def begin(
        self,
    ) -> AsyncIterator[AsyncSession]:
        self.begin_calls += 1

        yield self.session


def create_test_dependencies() -> tuple[
    RecordingSessionFactory,
    AsyncMock,
    ResearchRunRepository,
]:
    session_mock = AsyncMock(
        spec=AsyncSession,
    )
    session = cast(
        AsyncSession,
        session_mock,
    )
    session_factory = RecordingSessionFactory(
        session,
    )

    repository_mock = AsyncMock(
        spec=ResearchRunRepository,
    )
    repository = cast(
        ResearchRunRepository,
        repository_mock,
    )

    return (
        session_factory,
        repository_mock,
        repository,
    )


@pytest.mark.anyio
async def test_store_creates_queued_run_in_transaction() -> None:
    session_factory, repository_mock, repository = create_test_dependencies()
    tenant_id = uuid4()
    user_id = uuid4()
    research_run_id = uuid4()
    research_run = ResearchRun(
        id=research_run_id,
        tenant_id=tenant_id,
        requested_by_user_id=user_id,
        query="Compare HTTP/2 and HTTP/3.",
        llm_provider="ollama",
        status="queued",
    )
    repository_mock.create.return_value = research_run
    repository_sessions: list[AsyncSession] = []

    def create_repository(
        session: AsyncSession,
    ) -> ResearchRunRepository:
        repository_sessions.append(session)

        return repository

    store = PostgresResearchRunStore(
        session_factory,
        create_repository,
    )

    result = await store.create_queued(
        tenant_id=tenant_id,
        requested_by_user_id=user_id,
        query="Compare HTTP/2 and HTTP/3.",
        llm_provider="ollama",
    )

    assert result == research_run_id
    assert session_factory.begin_calls == 1
    assert repository_sessions == [
        session_factory.session,
    ]
    repository_mock.create.assert_awaited_once_with(
        tenant_id=tenant_id,
        requested_by_user_id=user_id,
        query="Compare HTTP/2 and HTTP/3.",
        llm_provider="ollama",
        research_run_id=None,
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "transition",
    [
        "running",
        "completed",
    ],
)
async def test_store_commits_lifecycle_transition(
    transition: str,
) -> None:
    session_factory, repository_mock, repository = create_test_dependencies()
    tenant_id = uuid4()
    research_run_id = uuid4()
    store = PostgresResearchRunStore(
        session_factory,
        lambda _: repository,
    )

    if transition == "running":
        await store.mark_running(
            tenant_id=tenant_id,
            research_run_id=research_run_id,
        )

        repository_mock.mark_running.assert_awaited_once_with(
            tenant_id=tenant_id,
            research_run_id=research_run_id,
        )
    else:
        await store.mark_completed(
            tenant_id=tenant_id,
            research_run_id=research_run_id,
        )

        repository_mock.mark_completed.assert_awaited_once_with(
            tenant_id=tenant_id,
            research_run_id=research_run_id,
        )

    assert session_factory.begin_calls == 1


@pytest.mark.anyio
async def test_store_marks_run_failed_in_transaction() -> None:
    session_factory, repository_mock, repository = create_test_dependencies()
    tenant_id = uuid4()
    research_run_id = uuid4()
    store = PostgresResearchRunStore(
        session_factory,
        lambda _: repository,
    )

    await store.mark_failed(
        tenant_id=tenant_id,
        research_run_id=research_run_id,
        error_message="Tavily search provider timed out.",
    )

    assert session_factory.begin_calls == 1
    repository_mock.mark_failed.assert_awaited_once_with(
        tenant_id=tenant_id,
        research_run_id=research_run_id,
        error_message="Tavily search provider timed out.",
    )


@pytest.mark.anyio
async def test_store_completes_run_and_report_in_same_transaction() -> None:
    session_factory, repository_mock, repository = create_test_dependencies()
    report_repository_mock = AsyncMock(spec=ResearchReportRepository)
    report_repository = cast(ResearchReportRepository, report_repository_mock)
    tenant_id = uuid4()
    research_run_id = uuid4()
    state: ResearchState = {
        "query": "Compare HTTP/2 and HTTP/3.",
        "status": "research_report_completed",
        "report": "Durable report.",
    }
    run_repository_sessions: list[AsyncSession] = []
    report_repository_sessions: list[AsyncSession] = []

    def create_run_repository(session: AsyncSession) -> ResearchRunRepository:
        run_repository_sessions.append(session)
        return repository

    def create_report_repository(session: AsyncSession) -> ResearchReportRepository:
        report_repository_sessions.append(session)
        return report_repository

    store = PostgresResearchRunStore(
        session_factory,
        create_run_repository,
        create_report_repository,
    )

    await store.mark_completed(
        tenant_id=tenant_id,
        research_run_id=research_run_id,
        result=state,
    )

    assert session_factory.begin_calls == 1
    assert run_repository_sessions == [session_factory.session]
    assert report_repository_sessions == [session_factory.session]
    repository_mock.mark_completed.assert_awaited_once_with(
        tenant_id=tenant_id,
        research_run_id=research_run_id,
    )
    report_repository_mock.create_from_state.assert_awaited_once_with(
        tenant_id=tenant_id,
        research_run_id=research_run_id,
        state=state,
    )
