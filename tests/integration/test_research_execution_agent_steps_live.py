from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete

from app.core.config import settings
from app.db.models import ResearchRun, Tenant, User
from app.db.repositories import (
    ResearchAgentStepRepository,
    TenantRepository,
    UserRepository,
)
from app.db.session import create_database_engine, create_session_factory
from app.schemas.intent import IntentDecision
from app.services.research.execution import LangGraphResearchWorkflow, ResearchExecutionService
from app.services.research.postgres import (
    PostgresResearchAgentStepStore,
    PostgresResearchRunStore,
)
from app.workflow.graph import build_eight_agent_research_graph


async def unexpected(*_: object, **__: object) -> object:
    raise AssertionError("Deep-research agents must not run for the direct route.")


async def classify_direct(_: str) -> IntentDecision:
    return IntentDecision(route="direct", reason="Stable knowledge is sufficient.")


async def generate_direct_answer(query: str) -> str:
    return f"Direct: {query}"


def build_direct_route_workflow() -> LangGraphResearchWorkflow:
    graph = build_eight_agent_research_graph(
        classify_direct,
        unexpected,  # type: ignore[arg-type]
        generate_direct_answer,
        unexpected,  # type: ignore[arg-type]
        unexpected,  # type: ignore[arg-type]
        unexpected,  # type: ignore[arg-type]
        unexpected,  # type: ignore[arg-type]
        unexpected,  # type: ignore[arg-type]
        unexpected,  # type: ignore[arg-type]
        unexpected,  # type: ignore[arg-type]
    )

    async def close() -> None:
        return None

    return LangGraphResearchWorkflow(graph, close)


@pytest.mark.integration
@pytest.mark.anyio
async def test_research_execution_writes_a_live_agent_step_trace() -> None:
    """Verify execute() durably traces each canonical agent step in Postgres."""

    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    engine = create_database_engine(echo=False)
    session_factory = create_session_factory(engine)
    tenant_id: UUID | None = None

    try:
        async with session_factory.begin() as session:
            unique_suffix = uuid4().hex[:12]
            tenant = await TenantRepository(session).create(
                slug=f"agent-step-trace-{unique_suffix}",
                name="Agent Step Trace Integration Test",
            )
            user = await UserRepository(session).create(
                tenant_id=tenant.id,
                email=f"engineer-{unique_suffix}@example.com",
                password_hash="test-password-hash",
                display_name="Integration Test Engineer",
            )
            tenant_id = tenant.id
            user_id = user.id

        workflow = build_direct_route_workflow()
        run_store = PostgresResearchRunStore(session_factory)
        agent_step_store = PostgresResearchAgentStepStore(session_factory)
        service = ResearchExecutionService(
            run_store,
            lambda _: workflow,
            agent_step_store=agent_step_store,
        )

        result = await service.execute(
            tenant_id=tenant_id,
            requested_by_user_id=user_id,
            query="Explain idempotency.",
            llm_provider="qwen",
        )

        assert result.state["answer"] == "Direct: Explain idempotency."

        async with session_factory() as session:
            steps = await ResearchAgentStepRepository(session).list_for_run(
                tenant_id=tenant_id,
                research_run_id=result.research_run_id,
            )

        assert [(step.agent_role, step.status) for step in steps] == [
            ("intent_router", "started"),
            ("intent_router", "completed"),
            ("direct_answer", "started"),
            ("direct_answer", "completed"),
        ]
        assert [step.sequence for step in steps] == [1, 2, 3, 4]
    finally:
        if tenant_id is not None:
            async with session_factory.begin() as session:
                await session.execute(delete(ResearchRun).where(ResearchRun.tenant_id == tenant_id))
                await session.execute(delete(User).where(User.tenant_id == tenant_id))
                await session.execute(delete(Tenant).where(Tenant.id == tenant_id))

        await engine.dispose()
