from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ClauseElement

from app.db.models import ResearchWorkerLease
from app.db.repositories import ResearchDurabilityRepository


def create_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.mark.anyio
async def test_repository_appends_checkpoint_without_committing() -> None:
    session = create_session()
    tenant_id = uuid4()
    run_id = uuid4()
    repository = ResearchDurabilityRepository(session)

    checkpoint = await repository.append_checkpoint(
        tenant_id=tenant_id,
        research_run_id=run_id,
        sequence=2,
        node_name=" evidence_judge ",
        state={"query": "Compare queue ownership.", "status": "evidence_judged"},
    )

    assert checkpoint.tenant_id == tenant_id
    assert checkpoint.research_run_id == run_id
    assert checkpoint.sequence == 2
    assert checkpoint.node_name == "evidence_judge"
    session.add.assert_called_once_with(checkpoint)
    session.flush.assert_awaited_once_with()
    session.commit.assert_not_awaited()


@pytest.mark.anyio
async def test_repository_appends_normalized_audit_event() -> None:
    session = create_session()
    repository = ResearchDurabilityRepository(session)

    event = await repository.append_audit_event(
        tenant_id=uuid4(),
        research_run_id=uuid4(),
        event_type=" worker.claimed ",
        actor_type=" WORKER ",
        actor_id=" worker-1 ",
        details={"attempt": 1},
    )

    assert event.event_type == "worker.claimed"
    assert event.actor_type == "worker"
    assert event.actor_id == "worker-1"
    assert event.details == {"attempt": 1}
    session.add.assert_called_once_with(event)
    session.flush.assert_awaited_once_with()


@pytest.mark.anyio
async def test_claim_lease_uses_atomic_expired_only_upsert() -> None:
    session = create_session()
    tenant_id = uuid4()
    run_id = uuid4()
    token = uuid4()
    now = datetime(2026, 8, 5, 20, 0, tzinfo=UTC)
    lease = ResearchWorkerLease(
        tenant_id=tenant_id,
        research_run_id=run_id,
        worker_id="worker-a",
        lease_token=token,
        attempt=1,
        acquired_at=now,
        heartbeat_at=now,
        expires_at=now + timedelta(seconds=30),
    )
    session.scalar.return_value = lease
    repository = ResearchDurabilityRepository(session)

    result = await repository.claim_lease(
        tenant_id=tenant_id,
        research_run_id=run_id,
        worker_id=" worker-a ",
        ttl_seconds=30,
        now=now,
        lease_token=token,
    )

    assert result is lease
    statement = cast(ClauseElement, session.scalar.await_args.args[0])
    sql = str(statement)
    assert "ON CONFLICT (tenant_id, research_run_id) DO UPDATE" in sql
    assert "research_worker_leases.expires_at <=" in sql
    assert "RETURNING research_worker_leases" in sql


@pytest.mark.anyio
async def test_claim_lease_returns_none_when_active_owner_wins() -> None:
    session = create_session()
    session.scalar.return_value = None
    repository = ResearchDurabilityRepository(session)

    result = await repository.claim_lease(
        tenant_id=uuid4(),
        research_run_id=uuid4(),
        worker_id="worker-b",
        ttl_seconds=30,
    )

    assert result is None


@pytest.mark.anyio
async def test_renew_and_release_require_current_owner_token() -> None:
    session = create_session()
    tenant_id = uuid4()
    run_id = uuid4()
    token = uuid4()
    now = datetime(2026, 8, 5, 20, 0, tzinfo=UTC)
    lease = Mock(spec=ResearchWorkerLease)
    session.scalar.side_effect = [lease, run_id, None]
    repository = ResearchDurabilityRepository(session)

    renewed = await repository.renew_lease(
        tenant_id=tenant_id,
        research_run_id=run_id,
        worker_id="worker-a",
        lease_token=token,
        ttl_seconds=30,
        now=now,
    )
    released = await repository.release_lease(
        tenant_id=tenant_id,
        research_run_id=run_id,
        worker_id="worker-a",
        lease_token=token,
    )
    stale_release = await repository.release_lease(
        tenant_id=tenant_id,
        research_run_id=run_id,
        worker_id="worker-a",
        lease_token=token,
    )

    assert renewed is lease
    assert released is True
    assert stale_release is False
    renew_statement = cast(ClauseElement, session.scalar.await_args_list[0].args[0])
    release_statement = cast(ClauseElement, session.scalar.await_args_list[1].args[0])
    assert "lease_token" in str(renew_statement)
    assert "research_runs.status" in str(renew_statement)
    assert "lease_token" in str(release_statement)


@pytest.mark.parametrize(
    ("method", "kwargs"),
    [
        (
            "claim_lease",
            {"worker_id": "", "ttl_seconds": 30},
        ),
        (
            "claim_lease",
            {"worker_id": "worker", "ttl_seconds": 0},
        ),
        (
            "renew_lease",
            {"worker_id": "worker", "lease_token": uuid4(), "ttl_seconds": 3601},
        ),
    ],
)
@pytest.mark.anyio
async def test_lease_operations_validate_bounds(
    method: str,
    kwargs: dict[str, object],
) -> None:
    repository = ResearchDurabilityRepository(create_session())

    with pytest.raises(ValueError):
        await getattr(repository, method)(
            tenant_id=uuid4(),
            research_run_id=uuid4(),
            **kwargs,
        )
