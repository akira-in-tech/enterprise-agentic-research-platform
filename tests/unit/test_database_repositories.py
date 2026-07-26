import asyncio
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import (
    ResearchRunRepository,
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
