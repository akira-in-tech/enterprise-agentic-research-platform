import asyncio
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
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
from app.main import app


async def create_test_identity() -> tuple[
    UUID,
    UUID,
]:
    engine = create_database_engine(
        echo=False,
    )
    session_factory = create_session_factory(
        engine,
    )

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
                slug=f"research-api-{unique_suffix}",
                name="Research API Live Test",
            )
            user = await user_repository.create(
                tenant_id=tenant.id,
                email=f"api-{unique_suffix}@example.com",
                display_name="API Integration Engineer",
            )

            return (
                tenant.id,
                user.id,
            )
    finally:
        await engine.dispose()


async def load_research_run(
    *,
    tenant_id: UUID,
    research_run_id: UUID,
) -> ResearchRun | None:
    engine = create_database_engine(
        echo=False,
    )
    session_factory = create_session_factory(
        engine,
    )

    try:
        async with session_factory() as session:
            repository = ResearchRunRepository(
                session,
            )

            return await repository.get_for_tenant(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
            )
    finally:
        await engine.dispose()


async def delete_test_identity(
    tenant_id: UUID,
) -> None:
    engine = create_database_engine(
        echo=False,
    )
    session_factory = create_session_factory(
        engine,
    )

    try:
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
    finally:
        await engine.dispose()


@pytest.mark.integration
def test_research_api_live_qwen_round_trip() -> None:
    """Verify the real API, Qwen workflow and PostgreSQL round trip."""

    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    tenant_id, user_id = asyncio.run(create_test_identity())

    try:
        with TestClient(app) as client:
            response = client.post(
                "/research-runs",
                headers={
                    "X-Tenant-ID": str(tenant_id),
                    "X-User-ID": str(user_id),
                },
                json={
                    "query": "What is a mutex?",
                    "llm_provider": "qwen",
                },
            )

        assert response.status_code == 200

        body = response.json()
        research_run_id = UUID(body["research_run_id"])

        assert body["llm_provider"] == "ollama"
        assert body["status"] == "completed"
        assert body["route"] == "direct"
        assert body["workflow_status"] == ("direct_answer_completed")
        assert body["answer"]

        stored_run = asyncio.run(
            load_research_run(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
            )
        )

        assert stored_run is not None
        assert stored_run.query == "What is a mutex?"
        assert stored_run.llm_provider == "ollama"
        assert stored_run.status == "completed"
        assert stored_run.requested_by_user_id == user_id
        assert stored_run.started_at is not None
        assert stored_run.completed_at is not None
        assert stored_run.error_message is None
    finally:
        asyncio.run(
            delete_test_identity(
                tenant_id,
            )
        )
