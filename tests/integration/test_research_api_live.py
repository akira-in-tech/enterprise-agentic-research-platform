import asyncio
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.core.config import settings
from app.db.models import ResearchRun, Tenant, User
from app.db.repositories import ResearchRunRepository
from app.db.session import (
    create_database_engine,
    create_session_factory,
)
from app.main import app
from app.services.auth import AuthService
from app.services.cache import (
    RedisConnection,
    create_research_idempotency_redis_key,
    create_research_result_cache_key,
)


async def create_test_identity() -> tuple[
    UUID,
    UUID,
    str,
]:
    """Register a fresh tenant/user through AuthService and return a live session token."""

    engine = create_database_engine(
        echo=False,
    )
    session_factory = create_session_factory(
        engine,
    )
    auth_service = AuthService(
        session_factory,
    )

    try:
        unique_suffix = uuid4().hex[:12]

        authenticated_session = await auth_service.register(
            email=f"api-{unique_suffix}@example.com",
            password="correct-horse-battery",
            tenant_name=f"Research API Live Test {unique_suffix}",
            display_name="API Integration Engineer",
        )

        return (
            authenticated_session.identity.tenant.id,
            authenticated_session.identity.user.id,
            authenticated_session.token,
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


async def count_research_runs(
    *,
    tenant_id: UUID,
) -> int:
    """Count durable runs created for one test tenant."""

    engine = create_database_engine(
        echo=False,
    )
    session_factory = create_session_factory(
        engine,
    )

    try:
        async with session_factory() as session:
            count = await session.scalar(
                select(
                    func.count(),
                )
                .select_from(ResearchRun)
                .where(
                    ResearchRun.tenant_id == tenant_id,
                )
            )

            return count or 0
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


async def delete_test_cache(
    *,
    tenant_id: UUID,
    query: str,
) -> None:
    """Delete the Redis entry created by the live API test."""

    connection = RedisConnection.from_url()
    cache_key = create_research_result_cache_key(
        tenant_id=tenant_id,
        llm_provider="ollama",
        query=query,
    )

    try:
        await connection.delete(
            key=cache_key,
        )
    finally:
        await connection.close()


async def delete_test_idempotency_record(
    *,
    tenant_id: UUID,
    client_key: str,
) -> None:
    """Delete the Redis idempotency entry created by a live test."""

    connection = RedisConnection.from_url()
    redis_key = create_research_idempotency_redis_key(
        tenant_id=tenant_id,
        client_key=client_key,
    )

    try:
        await connection.delete(
            key=redis_key,
        )
    finally:
        await connection.close()


@pytest.mark.integration
def test_research_api_live_qwen_round_trip() -> None:
    """Verify PostgreSQL, Qwen and Redis through the real API."""

    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    tenant_id, user_id, session_token = asyncio.run(create_test_identity())
    query = "What is a mutex?"

    try:
        asyncio.run(
            delete_test_cache(
                tenant_id=tenant_id,
                query=query,
            )
        )

        with TestClient(app) as client:
            client.cookies.set(
                settings.session_cookie_name,
                session_token,
            )
            first_response = client.post(
                "/research-runs",
                json={
                    "query": query,
                    "llm_provider": "qwen",
                },
            )
            second_response = client.post(
                "/research-runs",
                json={
                    "query": query,
                    "llm_provider": "qwen",
                },
            )

        assert first_response.status_code == 200
        assert second_response.status_code == 200

        first_body = first_response.json()
        second_body = second_response.json()

        assert first_body["cache_hit"] is False
        assert second_body["cache_hit"] is True

        for body in (
            first_body,
            second_body,
        ):
            assert body["llm_provider"] == "ollama"
            assert body["status"] == "completed"
            assert body["route"] == "direct"
            assert body["workflow_status"] == ("direct_answer_completed")
            assert body["answer"]

        first_research_run_id = UUID(first_body["research_run_id"])
        second_research_run_id = UUID(second_body["research_run_id"])

        assert first_research_run_id != second_research_run_id

        first_stored_run = asyncio.run(
            load_research_run(
                tenant_id=tenant_id,
                research_run_id=first_research_run_id,
            )
        )
        second_stored_run = asyncio.run(
            load_research_run(
                tenant_id=tenant_id,
                research_run_id=second_research_run_id,
            )
        )

        assert first_stored_run is not None
        assert second_stored_run is not None

        for stored_run in (
            first_stored_run,
            second_stored_run,
        ):
            assert stored_run.query == query
            assert stored_run.llm_provider == "ollama"
            assert stored_run.status == "completed"
            assert stored_run.requested_by_user_id == user_id
            assert stored_run.started_at is not None
            assert stored_run.completed_at is not None
            assert stored_run.error_message is None

    finally:
        try:
            asyncio.run(
                delete_test_cache(
                    tenant_id=tenant_id,
                    query=query,
                )
            )
        finally:
            asyncio.run(
                delete_test_identity(
                    tenant_id,
                )
            )


@pytest.mark.integration
def test_research_api_live_idempotency_replay_and_conflict() -> None:
    """Verify replay, conflict and one durable run through the API."""

    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    tenant_id, user_id, session_token = asyncio.run(create_test_identity())
    query = "Explain idempotency in REST APIs."
    conflicting_query = "Explain Linux epoll."
    client_key = f"live-api-{uuid4().hex}"

    try:
        asyncio.run(
            delete_test_cache(
                tenant_id=tenant_id,
                query=query,
            )
        )
        asyncio.run(
            delete_test_idempotency_record(
                tenant_id=tenant_id,
                client_key=client_key,
            )
        )

        with TestClient(app) as client:
            client.cookies.set(
                settings.session_cookie_name,
                session_token,
            )
            headers = {
                "Idempotency-Key": client_key,
            }

            first_response = client.post(
                "/research-runs",
                headers=headers,
                json={
                    "query": query,
                    "llm_provider": "qwen",
                },
            )
            replay_response = client.post(
                "/research-runs",
                headers=headers,
                json={
                    "query": query,
                    "llm_provider": "qwen",
                },
            )
            conflict_response = client.post(
                "/research-runs",
                headers=headers,
                json={
                    "query": conflicting_query,
                    "llm_provider": "qwen",
                },
            )

        assert first_response.status_code == 200
        assert replay_response.status_code == 200
        assert conflict_response.status_code == 409

        first_body = first_response.json()
        replay_body = replay_response.json()
        conflict_body = conflict_response.json()

        assert first_body["idempotency_replayed"] is False
        assert replay_body["idempotency_replayed"] is True

        assert first_body["research_run_id"] == (replay_body["research_run_id"])
        assert first_body["answer"] == replay_body["answer"]
        assert first_body["llm_provider"] == "ollama"
        assert replay_body["llm_provider"] == "ollama"
        assert first_body["status"] == "completed"
        assert replay_body["status"] == "completed"

        assert conflict_body["detail"] == (
            "Idempotency key was already used for a different research request."
        )

        research_run_id = UUID(first_body["research_run_id"])
        stored_run = asyncio.run(
            load_research_run(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
            )
        )
        stored_run_count = asyncio.run(
            count_research_runs(
                tenant_id=tenant_id,
            )
        )

        assert stored_run is not None
        assert stored_run.query == query
        assert stored_run.status == "completed"
        assert stored_run.requested_by_user_id == user_id
        assert stored_run_count == 1

    finally:
        try:
            asyncio.run(
                delete_test_idempotency_record(
                    tenant_id=tenant_id,
                    client_key=client_key,
                )
            )
        finally:
            try:
                asyncio.run(
                    delete_test_cache(
                        tenant_id=tenant_id,
                        query=query,
                    )
                )
            finally:
                asyncio.run(
                    delete_test_identity(
                        tenant_id,
                    )
                )
