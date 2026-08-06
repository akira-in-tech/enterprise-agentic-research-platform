from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete

from app.core.config import settings
from app.db.models import ResearchRun, Tenant, User
from app.db.repositories import (
    ResearchRunRepository,
    TenantRepository,
    UserRepository,
)
from app.db.session import (
    create_database_engine,
    create_session_factory,
)
from app.services.llm.factory import CanonicalLLMProvider
from app.services.research.execution import (
    ResearchExecutionService,
)
from app.services.research.postgres import (
    PostgresResearchRunStore,
)
from app.workflow.state import ResearchState


class SuccessfulResearchWorkflow:
    async def ainvoke(
        self,
        state: ResearchState,
    ) -> ResearchState:
        return {
            "query": state["query"],
            "route": "direct",
            "route_reason": ("The question can be answered using stable knowledge."),
            "answer": ("epoll is Linux's scalable I/O event notification interface."),
            "status": "direct_answer_completed",
        }

    async def close(self) -> None:
        """Release no-op integration workflow resources."""


@pytest.mark.integration
@pytest.mark.anyio
async def test_research_execution_persists_provider_and_lifecycle() -> None:
    """Verify one execution against a real PostgreSQL database."""

    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    engine = create_database_engine(
        echo=False,
    )
    session_factory = create_session_factory(
        engine,
    )
    tenant_id: UUID | None = None

    try:
        async with session_factory.begin() as session:
            tenant_repository = TenantRepository(
                session,
            )
            user_repository = UserRepository(
                session,
            )
            unique_suffix = uuid4().hex[:12]

            tenant = await tenant_repository.create(
                slug=f"research-execution-{unique_suffix}",
                name="Research Execution Integration Test",
            )
            user = await user_repository.create(
                tenant_id=tenant.id,
                email=f"engineer-{unique_suffix}@example.com",
                password_hash="test-password-hash",
                display_name="Integration Test Engineer",
            )

            tenant_id = tenant.id
            user_id = user.id

        workflow = SuccessfulResearchWorkflow()
        provider_calls: list[CanonicalLLMProvider] = []

        def create_workflow(
            provider: CanonicalLLMProvider,
        ) -> SuccessfulResearchWorkflow:
            provider_calls.append(provider)

            return workflow

        store = PostgresResearchRunStore(
            session_factory,
        )
        service = ResearchExecutionService(
            store,
            create_workflow,
        )

        result = await service.execute(
            tenant_id=tenant_id,
            requested_by_user_id=user_id,
            query="  Explain Linux epoll.  ",
            llm_provider="qwen",
        )

        assert result.llm_provider == "ollama"
        assert result.state["route"] == "direct"
        assert result.state["status"] == ("direct_answer_completed")
        assert provider_calls == [
            "ollama",
        ]

        async with session_factory() as session:
            repository = ResearchRunRepository(
                session,
            )
            stored_run = await repository.get_for_tenant(
                tenant_id=tenant_id,
                research_run_id=result.research_run_id,
            )

            assert stored_run is not None
            assert stored_run.query == "Explain Linux epoll."
            assert stored_run.llm_provider == "ollama"
            assert stored_run.status == "completed"
            assert stored_run.requested_by_user_id == user_id
            assert stored_run.started_at is not None
            assert stored_run.completed_at is not None
            assert stored_run.error_message is None
    finally:
        if tenant_id is not None:
            async with session_factory.begin() as session:
                await session.execute(
                    delete(ResearchRun).where(
                        ResearchRun.tenant_id == tenant_id,
                    )
                )
                await session.execute(
                    delete(User).where(
                        User.tenant_id == tenant_id,
                    )
                )
                await session.execute(
                    delete(Tenant).where(
                        Tenant.id == tenant_id,
                    )
                )

        await engine.dispose()
