import asyncio
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.research import ResearchRun
from app.db.repositories import (
    ResearchRunRepository,
    ResearchRunTransitionError,
    TenantRepository,
    UserRepository,
)


def create_session_mock() -> tuple[
    AsyncSession,
    AsyncMock,
]:
    session_mock = AsyncMock(
        spec=AsyncSession,
    )

    return (
        cast(
            AsyncSession,
            session_mock,
        ),
        session_mock,
    )


def create_research_run(
    *,
    status: str,
) -> ResearchRun:
    return ResearchRun(
        id=uuid4(),
        tenant_id=uuid4(),
        query="Explain Linux epoll.",
        llm_provider="ollama",
        status=status,
    )


def test_tenant_repository_normalizes_and_flushes() -> None:
    session, session_mock = create_session_mock()
    repository = TenantRepository(session)

    tenant = asyncio.run(
        repository.create(
            slug="  HENNGE-Platform  ",
            name="  HENNGE Platform Engineering  ",
        )
    )

    assert tenant.slug == "hennge-platform"
    assert tenant.name == "HENNGE Platform Engineering"

    session_mock.add.assert_called_once_with(tenant)
    session_mock.flush.assert_awaited_once_with()
    session_mock.commit.assert_not_awaited()


@pytest.mark.parametrize(
    ("slug", "name", "expected_error"),
    [
        (
            "   ",
            "HENNGE",
            "slug must not be empty",
        ),
        (
            "hennge",
            "   ",
            "name must not be empty",
        ),
        (
            "a" * 101,
            "HENNGE",
            "slug must not exceed 100 characters",
        ),
        (
            "hennge",
            "a" * 201,
            "name must not exceed 200 characters",
        ),
    ],
)
def test_tenant_repository_rejects_invalid_values(
    slug: str,
    name: str,
    expected_error: str,
) -> None:
    session, session_mock = create_session_mock()
    repository = TenantRepository(session)

    with pytest.raises(
        ValueError,
        match=expected_error,
    ):
        asyncio.run(
            repository.create(
                slug=slug,
                name=name,
            )
        )

    session_mock.add.assert_not_called()
    session_mock.flush.assert_not_awaited()


def test_user_repository_normalizes_identity_fields() -> None:
    session, session_mock = create_session_mock()
    repository = UserRepository(session)
    tenant_id = uuid4()

    user = asyncio.run(
        repository.create(
            tenant_id=tenant_id,
            email="  Engineer@HENNGE.COM  ",
            display_name="  Platform Engineer  ",
        )
    )

    assert user.tenant_id == tenant_id
    assert user.email == "engineer@hennge.com"
    assert user.display_name == "Platform Engineer"

    session_mock.add.assert_called_once_with(user)
    session_mock.flush.assert_awaited_once_with()
    session_mock.commit.assert_not_awaited()


@pytest.mark.parametrize(
    ("email", "expected_error"),
    [
        (
            "   ",
            "email must not be empty",
        ),
        (
            "a" * 321,
            "email must not exceed 320 characters",
        ),
    ],
)
def test_user_repository_rejects_invalid_email(
    email: str,
    expected_error: str,
) -> None:
    session, session_mock = create_session_mock()
    repository = UserRepository(session)

    with pytest.raises(
        ValueError,
        match=expected_error,
    ):
        asyncio.run(
            repository.create(
                tenant_id=uuid4(),
                email=email,
            )
        )

    session_mock.add.assert_not_called()
    session_mock.flush.assert_not_awaited()


def test_research_run_repository_normalizes_and_flushes() -> None:
    session, session_mock = create_session_mock()
    repository = ResearchRunRepository(session)
    tenant_id = uuid4()
    user_id = uuid4()

    research_run = asyncio.run(
        repository.create(
            tenant_id=tenant_id,
            requested_by_user_id=user_id,
            query=("  Compare PostgreSQL B-tree and GIN indexes.  "),
            llm_provider="  OLLAMA  ",
        )
    )

    assert research_run.tenant_id == tenant_id
    assert research_run.requested_by_user_id == user_id
    assert research_run.query == ("Compare PostgreSQL B-tree and GIN indexes.")
    assert research_run.llm_provider == "ollama"
    assert research_run.status == "queued"

    session_mock.add.assert_called_once_with(research_run)
    session_mock.flush.assert_awaited_once_with()
    session_mock.commit.assert_not_awaited()


@pytest.mark.parametrize(
    ("query", "llm_provider", "expected_error"),
    [
        (
            "   ",
            "ollama",
            "query must not be empty",
        ),
        (
            "Explain HTTP/2.",
            "",
            "llm_provider must be",
        ),
        (
            "Explain HTTP/2.",
            "openai",
            "llm_provider must be",
        ),
    ],
)
def test_research_run_repository_rejects_invalid_input(
    query: str,
    llm_provider: str,
    expected_error: str,
) -> None:
    session, session_mock = create_session_mock()
    repository = ResearchRunRepository(session)

    with pytest.raises(
        ValueError,
        match=expected_error,
    ):
        asyncio.run(
            repository.create(
                tenant_id=uuid4(),
                query=query,
                llm_provider=llm_provider,
            )
        )

    session_mock.add.assert_not_called()
    session_mock.flush.assert_not_awaited()


@pytest.mark.parametrize(
    "limit",
    [
        0,
        101,
    ],
)
def test_research_run_repository_rejects_invalid_limit(
    limit: int,
) -> None:
    session, session_mock = create_session_mock()
    repository = ResearchRunRepository(session)

    with pytest.raises(
        ValueError,
        match="limit must be between 1 and 100",
    ):
        asyncio.run(
            repository.list_recent_for_tenant(
                tenant_id=uuid4(),
                limit=limit,
            )
        )

    session_mock.scalars.assert_not_awaited()


def test_research_run_repository_marks_run_running() -> None:
    session, session_mock = create_session_mock()
    repository = ResearchRunRepository(session)
    research_run = create_research_run(
        status="running",
    )
    session_mock.scalar.return_value = research_run

    result = asyncio.run(
        repository.mark_running(
            tenant_id=research_run.tenant_id,
            research_run_id=research_run.id,
        )
    )

    assert result is research_run
    session_mock.scalar.assert_awaited_once()
    session_mock.commit.assert_not_awaited()


def test_research_run_repository_marks_run_completed() -> None:
    session, session_mock = create_session_mock()
    repository = ResearchRunRepository(session)
    research_run = create_research_run(
        status="completed",
    )
    session_mock.scalar.return_value = research_run

    result = asyncio.run(
        repository.mark_completed(
            tenant_id=research_run.tenant_id,
            research_run_id=research_run.id,
        )
    )

    assert result is research_run
    session_mock.scalar.assert_awaited_once()
    session_mock.commit.assert_not_awaited()


def test_research_run_repository_marks_run_failed() -> None:
    session, session_mock = create_session_mock()
    repository = ResearchRunRepository(session)
    research_run = create_research_run(
        status="failed",
    )
    research_run.error_message = "Search provider failed."
    session_mock.scalar.return_value = research_run

    result = asyncio.run(
        repository.mark_failed(
            tenant_id=research_run.tenant_id,
            research_run_id=research_run.id,
            error_message="  Search provider failed.  ",
        )
    )

    assert result is research_run
    assert result.error_message == "Search provider failed."
    session_mock.scalar.assert_awaited_once()
    session_mock.commit.assert_not_awaited()


def test_research_run_repository_marks_active_run_cancelled() -> None:
    session, session_mock = create_session_mock()
    repository = ResearchRunRepository(session)
    research_run = create_research_run(status="cancelled")
    session_mock.scalar.return_value = research_run

    result = asyncio.run(
        repository.mark_cancelled(
            tenant_id=research_run.tenant_id,
            research_run_id=research_run.id,
        )
    )

    assert result is research_run
    session_mock.scalar.assert_awaited_once()
    session_mock.commit.assert_not_awaited()


def test_research_run_repository_rejects_invalid_transition() -> None:
    session, session_mock = create_session_mock()
    repository = ResearchRunRepository(session)
    session_mock.scalar.return_value = None

    with pytest.raises(
        ResearchRunTransitionError,
        match="cannot transition to running",
    ):
        asyncio.run(
            repository.mark_running(
                tenant_id=uuid4(),
                research_run_id=uuid4(),
            )
        )

    session_mock.commit.assert_not_awaited()


@pytest.mark.parametrize(
    ("error_message", "expected_error"),
    [
        (
            "   ",
            "error_message must not be empty",
        ),
        (
            "a" * 4_001,
            "error_message must not exceed 4000 characters",
        ),
    ],
)
def test_research_run_repository_rejects_invalid_failure(
    error_message: str,
    expected_error: str,
) -> None:
    session, session_mock = create_session_mock()
    repository = ResearchRunRepository(session)

    with pytest.raises(
        ValueError,
        match=expected_error,
    ):
        asyncio.run(
            repository.mark_failed(
                tenant_id=uuid4(),
                research_run_id=uuid4(),
                error_message=error_message,
            )
        )

    session_mock.scalar.assert_not_awaited()
