from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.core.config import settings
from app.db.models import Tenant
from app.db.repositories import (
    ResearchDurabilityRepository,
    ResearchRunRepository,
    TenantRepository,
)
from app.db.session import create_database_engine, create_session_factory


@pytest.mark.integration
@pytest.mark.anyio
async def test_research_durability_live_claim_checkpoint_and_audit() -> None:
    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    engine = create_database_engine(echo=False)
    session_factory = create_session_factory(engine)
    tenant_id = None
    now = datetime.now(UTC)
    first_token = uuid4()
    second_token = uuid4()

    try:
        async with session_factory() as session:
            async with session.begin():
                tenant = await TenantRepository(session).create(
                    slug=f"durability-{uuid4().hex[:12]}",
                    name="Durability Integration Test",
                )
                run = await ResearchRunRepository(session).create(
                    tenant_id=tenant.id,
                    query="Verify durable worker ownership.",
                    llm_provider="ollama",
                )
                tenant_id = tenant.id
                run_id = run.id

        assert tenant_id is not None

        async with session_factory() as session:
            async with session.begin():
                first_lease = await ResearchDurabilityRepository(session).claim_lease(
                    tenant_id=tenant_id,
                    research_run_id=run_id,
                    worker_id="worker-a",
                    ttl_seconds=30,
                    now=now,
                    lease_token=first_token,
                )
                assert first_lease is not None
                assert first_lease.attempt == 1

        async with session_factory() as session:
            async with session.begin():
                active_conflict = await ResearchDurabilityRepository(session).claim_lease(
                    tenant_id=tenant_id,
                    research_run_id=run_id,
                    worker_id="worker-b",
                    ttl_seconds=30,
                    now=now + timedelta(seconds=1),
                )
                assert active_conflict is None

        reclaimed_at = now + timedelta(seconds=31)
        async with session_factory() as session:
            async with session.begin():
                repository = ResearchDurabilityRepository(session)
                second_lease = await repository.claim_lease(
                    tenant_id=tenant_id,
                    research_run_id=run_id,
                    worker_id="worker-b",
                    ttl_seconds=30,
                    now=reclaimed_at,
                    lease_token=second_token,
                )
                assert second_lease is not None
                assert second_lease.attempt == 2
                assert (
                    await repository.release_lease(
                        tenant_id=tenant_id,
                        research_run_id=run_id,
                        worker_id="worker-a",
                        lease_token=first_token,
                    )
                    is False
                )
                await repository.append_checkpoint(
                    tenant_id=tenant_id,
                    research_run_id=run_id,
                    sequence=1,
                    node_name="planner",
                    state={"query": "Verify durable worker ownership.", "status": "planned"},
                )
                await repository.append_checkpoint(
                    tenant_id=tenant_id,
                    research_run_id=run_id,
                    sequence=2,
                    node_name="evidence_judge",
                    state={"query": "Verify durable worker ownership.", "status": "judged"},
                )
                await repository.append_audit_event(
                    tenant_id=tenant_id,
                    research_run_id=run_id,
                    event_type="worker.reclaimed",
                    actor_type="worker",
                    actor_id="worker-b",
                    details={"attempt": 2},
                )

        async with session_factory() as session:
            repository = ResearchDurabilityRepository(session)
            checkpoint = await repository.get_latest_checkpoint(
                tenant_id=tenant_id,
                research_run_id=run_id,
            )
            events = await repository.list_audit_events(
                tenant_id=tenant_id,
                research_run_id=run_id,
            )

            assert checkpoint is not None
            assert checkpoint.sequence == 2
            assert checkpoint.state["status"] == "judged"
            assert [(event.event_type, event.details) for event in events] == [
                ("worker.reclaimed", {"attempt": 2})
            ]
    finally:
        if tenant_id is not None:
            async with session_factory() as session:
                async with session.begin():
                    await session.execute(delete(Tenant).where(Tenant.id == tenant_id))
        await engine.dispose()
