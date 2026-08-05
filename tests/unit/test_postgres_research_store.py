from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ResearchCheckpoint, ResearchRun, ResearchWorkerLease
from app.db.repositories import (
    ResearchDurabilityRepository,
    ResearchReportRepository,
    ResearchRunRepository,
    ResearchRunTransitionError,
)
from app.services.research.postgres import (
    PostgresResearchDurabilityStore,
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
async def test_store_returns_tenant_scoped_run() -> None:
    session_factory, repository_mock, repository = create_test_dependencies()
    tenant_id = uuid4()
    research_run_id = uuid4()
    research_run = ResearchRun(
        id=research_run_id,
        tenant_id=tenant_id,
        query="Compare HTTP/2 and HTTP/3.",
        llm_provider="anthropic",
        status="completed",
    )
    repository_mock.get_for_tenant.return_value = research_run
    store = PostgresResearchRunStore(session_factory, lambda _: repository)

    result = await store.get(
        tenant_id=tenant_id,
        research_run_id=research_run_id,
    )

    assert result is research_run
    assert session_factory.begin_calls == 1
    repository_mock.get_for_tenant.assert_awaited_once_with(
        tenant_id=tenant_id,
        research_run_id=research_run_id,
    )


@pytest.mark.anyio
async def test_store_returns_none_for_missing_run() -> None:
    session_factory, repository_mock, repository = create_test_dependencies()
    repository_mock.get_for_tenant.return_value = None
    store = PostgresResearchRunStore(session_factory, lambda _: repository)

    result = await store.get(
        tenant_id=uuid4(),
        research_run_id=uuid4(),
    )

    assert result is None


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
async def test_store_marks_active_run_cancelled_in_transaction() -> None:
    session_factory, repository_mock, repository = create_test_dependencies()
    tenant_id = uuid4()
    research_run_id = uuid4()
    store = PostgresResearchRunStore(session_factory, lambda _: repository)

    cancelled = await store.mark_cancelled(
        tenant_id=tenant_id,
        research_run_id=research_run_id,
    )

    assert cancelled is True
    assert session_factory.begin_calls == 1
    repository_mock.mark_cancelled.assert_awaited_once_with(
        tenant_id=tenant_id,
        research_run_id=research_run_id,
    )


@pytest.mark.anyio
async def test_store_rejects_cancelling_terminal_or_missing_run() -> None:
    session_factory, repository_mock, repository = create_test_dependencies()
    repository_mock.mark_cancelled.side_effect = ResearchRunTransitionError(
        "Research run is missing or cannot transition to cancelled."
    )
    store = PostgresResearchRunStore(session_factory, lambda _: repository)

    cancelled = await store.mark_cancelled(
        tenant_id=uuid4(),
        research_run_id=uuid4(),
    )

    assert cancelled is False


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


@pytest.mark.anyio
async def test_durability_store_claims_and_maps_worker_lease() -> None:
    session_mock = AsyncMock(spec=AsyncSession)
    session = cast(AsyncSession, session_mock)
    session_factory = RecordingSessionFactory(session)
    repository_mock = AsyncMock(spec=ResearchDurabilityRepository)
    repository = cast(ResearchDurabilityRepository, repository_mock)
    tenant_id = uuid4()
    research_run_id = uuid4()
    lease_token = uuid4()
    acquired_at = datetime.now(UTC)
    repository_mock.claim_lease.return_value = ResearchWorkerLease(
        tenant_id=tenant_id,
        research_run_id=research_run_id,
        worker_id="worker-1",
        lease_token=lease_token,
        attempt=2,
        acquired_at=acquired_at,
        heartbeat_at=acquired_at,
        expires_at=acquired_at + timedelta(seconds=30),
    )
    store = PostgresResearchDurabilityStore(
        session_factory,
        lambda _: repository,
    )

    result = await store.claim_lease(
        tenant_id=tenant_id,
        research_run_id=research_run_id,
        worker_id="worker-1",
        ttl_seconds=30,
    )

    assert result is not None
    assert result.lease_token == lease_token
    assert result.attempt == 2
    assert session_factory.begin_calls == 1
    repository_mock.claim_lease.assert_awaited_once_with(
        tenant_id=tenant_id,
        research_run_id=research_run_id,
        worker_id="worker-1",
        ttl_seconds=30,
    )


@pytest.mark.anyio
async def test_durability_store_serializes_checkpoint_in_transaction() -> None:
    session_mock = AsyncMock(spec=AsyncSession)
    session = cast(AsyncSession, session_mock)
    session_factory = RecordingSessionFactory(session)
    repository_mock = AsyncMock(spec=ResearchDurabilityRepository)
    repository = cast(ResearchDurabilityRepository, repository_mock)
    tenant_id = uuid4()
    research_run_id = uuid4()
    checkpoint_id = uuid4()
    created_at = datetime.now(UTC)
    repository_mock.append_checkpoint.return_value = ResearchCheckpoint(
        id=checkpoint_id,
        tenant_id=tenant_id,
        research_run_id=research_run_id,
        sequence=3,
        node_name="writer",
        state={"tenant_id": str(tenant_id), "status": "completed"},
        created_at=created_at,
    )
    store = PostgresResearchDurabilityStore(
        session_factory,
        lambda _: repository,
    )

    result = await store.append_checkpoint(
        tenant_id=tenant_id,
        research_run_id=research_run_id,
        sequence=3,
        node_name="writer",
        state={"tenant_id": tenant_id, "status": "completed"},
    )

    assert result.sequence == 3
    assert result.state["tenant_id"] == str(tenant_id)
    repository_mock.append_checkpoint.assert_awaited_once_with(
        tenant_id=tenant_id,
        research_run_id=research_run_id,
        sequence=3,
        node_name="writer",
        state={"tenant_id": str(tenant_id), "status": "completed"},
    )


@pytest.mark.anyio
async def test_durability_store_renews_releases_and_audits() -> None:
    session_mock = AsyncMock(spec=AsyncSession)
    session = cast(AsyncSession, session_mock)
    session_factory = RecordingSessionFactory(session)
    repository_mock = AsyncMock(spec=ResearchDurabilityRepository)
    repository = cast(ResearchDurabilityRepository, repository_mock)
    repository_mock.renew_lease.return_value = None
    repository_mock.release_lease.return_value = True
    tenant_id = uuid4()
    research_run_id = uuid4()
    lease_token = uuid4()
    store = PostgresResearchDurabilityStore(
        session_factory,
        lambda _: repository,
    )

    renewed = await store.renew_lease(
        tenant_id=tenant_id,
        research_run_id=research_run_id,
        worker_id="worker-1",
        lease_token=lease_token,
        ttl_seconds=30,
    )
    released = await store.release_lease(
        tenant_id=tenant_id,
        research_run_id=research_run_id,
        worker_id="worker-1",
        lease_token=lease_token,
    )
    await store.append_audit_event(
        tenant_id=tenant_id,
        research_run_id=research_run_id,
        event_type="worker.claimed",
        actor_type="worker",
        actor_id="worker-1",
        details={"lease_token": lease_token},
    )

    assert renewed is None
    assert released is True
    assert session_factory.begin_calls == 3
    repository_mock.append_audit_event.assert_awaited_once_with(
        tenant_id=tenant_id,
        research_run_id=research_run_id,
        event_type="worker.claimed",
        actor_type="worker",
        actor_id="worker-1",
        details={"lease_token": str(lease_token)},
    )
