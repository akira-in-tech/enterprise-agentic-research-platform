from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete

from app.core.config import settings
from app.db.models import ResearchRun, Tenant, User
from app.db.repositories import (
    ResearchAgentStepRepository,
    ResearchRunRepository,
    TenantRepository,
    UserRepository,
)
from app.db.session import create_database_engine, create_session_factory


@pytest.mark.integration
@pytest.mark.anyio
async def test_agent_step_repository_live_round_trip() -> None:
    """Verify durable, tenant-scoped, ordered agent-step persistence."""

    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    engine = create_database_engine(echo=False)
    session_factory = create_session_factory(engine)
    tenant_id: UUID | None = None

    try:
        async with session_factory() as session:
            async with session.begin():
                unique_suffix = uuid4().hex[:12]
                tenant = await TenantRepository(session).create(
                    slug=f"acme-platform-{unique_suffix}",
                    name="ACME Platform Engineering",
                )
                tenant_id = tenant.id
                user = await UserRepository(session).create(
                    tenant_id=tenant.id,
                    email=f"engineer-{unique_suffix}@acme.example",
                    display_name="ACME Engineer",
                )
                run = await ResearchRunRepository(session).create(
                    tenant_id=tenant.id,
                    requested_by_user_id=user.id,
                    query="Compare HTTP/2 and HTTP/3.",
                    llm_provider="anthropic",
                )

                repository = ResearchAgentStepRepository(session)
                await repository.append(
                    tenant_id=tenant.id,
                    research_run_id=run.id,
                    sequence=0,
                    agent_role="intent_router",
                    status="completed",
                    summary="Routed to deep_research.",
                )
                await repository.append(
                    tenant_id=tenant.id,
                    research_run_id=run.id,
                    sequence=1,
                    agent_role="planner",
                    status="completed",
                )

            async with session.begin():
                steps = await ResearchAgentStepRepository(session).list_for_run(
                    tenant_id=tenant.id,
                    research_run_id=run.id,
                )

        assert [step.agent_role for step in steps] == ["intent_router", "planner"]
        assert steps[0].sequence == 0
        assert steps[0].summary == "Routed to deep_research."
        assert steps[1].summary is None
    finally:
        if tenant_id is not None:
            async with session_factory() as cleanup_session:
                async with cleanup_session.begin():
                    await cleanup_session.execute(
                        delete(ResearchRun).where(ResearchRun.tenant_id == tenant_id)
                    )
                    await cleanup_session.execute(
                        delete(User).where(User.tenant_id == tenant_id)
                    )
                    await cleanup_session.execute(
                        delete(Tenant).where(Tenant.id == tenant_id)
                    )

        await engine.dispose()
