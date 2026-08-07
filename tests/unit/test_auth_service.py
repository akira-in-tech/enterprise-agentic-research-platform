from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Session, Tenant, User
from app.db.repositories import SessionRepository, TenantRepository, UserRepository
from app.services.auth.passwords import hash_password
from app.services.auth.service import (
    AuthService,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
)


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
    AsyncMock,
    AsyncMock,
]:
    session_mock = AsyncMock(spec=AsyncSession)
    session_factory = RecordingSessionFactory(cast(AsyncSession, session_mock))

    tenant_repository_mock = AsyncMock(spec=TenantRepository)
    user_repository_mock = AsyncMock(spec=UserRepository)
    session_repository_mock = AsyncMock(spec=SessionRepository)

    return (
        session_factory,
        tenant_repository_mock,
        user_repository_mock,
        session_repository_mock,
    )


def create_service(
    session_factory: RecordingSessionFactory,
    *,
    tenant_repository_mock: AsyncMock,
    user_repository_mock: AsyncMock,
    session_repository_mock: AsyncMock,
) -> AuthService:
    return AuthService(
        session_factory,
        tenant_repository_factory=lambda _: cast(TenantRepository, tenant_repository_mock),
        user_repository_factory=lambda _: cast(UserRepository, user_repository_mock),
        session_repository_factory=lambda _: cast(SessionRepository, session_repository_mock),
    )


def create_user(
    *,
    tenant_id: object,
    password: str,
) -> User:
    return User(
        id=uuid4(),
        tenant_id=tenant_id,
        email="engineer@acme.example",
        password_hash=hash_password(password),
        display_name="ACME Engineer",
    )


def create_tenant() -> Tenant:
    return Tenant(
        id=uuid4(),
        slug="acme-platform-a1b2c3d4",
        name="ACME Platform",
    )


@pytest.mark.anyio
async def test_register_creates_tenant_user_and_session() -> None:
    (
        session_factory,
        tenant_repository_mock,
        user_repository_mock,
        session_repository_mock,
    ) = create_test_dependencies()
    tenant = create_tenant()
    user_repository_mock.get_by_email.return_value = None
    tenant_repository_mock.create.return_value = tenant
    user_repository_mock.create.return_value = User(
        id=uuid4(),
        tenant_id=tenant.id,
        email="engineer@acme.example",
        password_hash="irrelevant-because-mocked",
        display_name="ACME Engineer",
    )
    service = create_service(
        session_factory,
        tenant_repository_mock=tenant_repository_mock,
        user_repository_mock=user_repository_mock,
        session_repository_mock=session_repository_mock,
    )

    result = await service.register(
        email="Engineer@ACME.example",
        password="correct-horse-battery",
        tenant_name="ACME Platform",
    )

    assert result.identity.tenant is tenant
    assert isinstance(
        result.token,
        str,
    )
    assert len(result.token) > 20
    assert result.expires_at > datetime.now(UTC)

    tenant_repository_mock.create.assert_awaited_once()
    assert tenant_repository_mock.create.await_args.kwargs["slug"].startswith("acme-platform-")
    session_repository_mock.create.assert_awaited_once()


@pytest.mark.anyio
async def test_register_rejects_duplicate_email() -> None:
    (
        session_factory,
        tenant_repository_mock,
        user_repository_mock,
        session_repository_mock,
    ) = create_test_dependencies()
    user_repository_mock.get_by_email.return_value = create_user(
        tenant_id=uuid4(),
        password="existing-password",
    )
    service = create_service(
        session_factory,
        tenant_repository_mock=tenant_repository_mock,
        user_repository_mock=user_repository_mock,
        session_repository_mock=session_repository_mock,
    )

    with pytest.raises(EmailAlreadyRegisteredError):
        await service.register(
            email="engineer@acme.example",
            password="correct-horse-battery",
            tenant_name="ACME Platform",
        )

    tenant_repository_mock.create.assert_not_awaited()


@pytest.mark.anyio
async def test_login_succeeds_with_correct_password() -> None:
    (
        session_factory,
        tenant_repository_mock,
        user_repository_mock,
        session_repository_mock,
    ) = create_test_dependencies()
    tenant = create_tenant()
    user = create_user(
        tenant_id=tenant.id,
        password="correct-horse-battery",
    )
    user_repository_mock.get_by_email.return_value = user
    tenant_repository_mock.get.return_value = tenant
    service = create_service(
        session_factory,
        tenant_repository_mock=tenant_repository_mock,
        user_repository_mock=user_repository_mock,
        session_repository_mock=session_repository_mock,
    )

    result = await service.login(
        email="engineer@acme.example",
        password="correct-horse-battery",
    )

    assert result.identity.user is user
    assert result.identity.tenant is tenant
    session_repository_mock.create.assert_awaited_once()


@pytest.mark.anyio
async def test_login_rejects_wrong_password() -> None:
    (
        session_factory,
        tenant_repository_mock,
        user_repository_mock,
        session_repository_mock,
    ) = create_test_dependencies()
    user_repository_mock.get_by_email.return_value = create_user(
        tenant_id=uuid4(),
        password="correct-horse-battery",
    )
    service = create_service(
        session_factory,
        tenant_repository_mock=tenant_repository_mock,
        user_repository_mock=user_repository_mock,
        session_repository_mock=session_repository_mock,
    )

    with pytest.raises(InvalidCredentialsError):
        await service.login(
            email="engineer@acme.example",
            password="wrong-password",
        )

    session_repository_mock.create.assert_not_awaited()


@pytest.mark.anyio
async def test_login_rejects_unknown_email() -> None:
    (
        session_factory,
        tenant_repository_mock,
        user_repository_mock,
        session_repository_mock,
    ) = create_test_dependencies()
    user_repository_mock.get_by_email.return_value = None
    service = create_service(
        session_factory,
        tenant_repository_mock=tenant_repository_mock,
        user_repository_mock=user_repository_mock,
        session_repository_mock=session_repository_mock,
    )

    with pytest.raises(InvalidCredentialsError):
        await service.login(
            email="nobody@acme.example",
            password="whatever-password",
        )

    session_repository_mock.create.assert_not_awaited()


@pytest.mark.anyio
async def test_logout_revokes_session() -> None:
    (
        session_factory,
        tenant_repository_mock,
        user_repository_mock,
        session_repository_mock,
    ) = create_test_dependencies()
    service = create_service(
        session_factory,
        tenant_repository_mock=tenant_repository_mock,
        user_repository_mock=user_repository_mock,
        session_repository_mock=session_repository_mock,
    )

    await service.logout(token="some-opaque-token")

    session_repository_mock.revoke.assert_awaited_once()
    assert session_repository_mock.revoke.await_args.kwargs["token_hash"] != "some-opaque-token"
    assert len(session_repository_mock.revoke.await_args.kwargs["token_hash"]) == 64


@pytest.mark.anyio
async def test_resolve_session_returns_identity_for_valid_token() -> None:
    (
        session_factory,
        tenant_repository_mock,
        user_repository_mock,
        session_repository_mock,
    ) = create_test_dependencies()
    user_id = uuid4()
    tenant_id = uuid4()
    session_repository_mock.get_by_token_hash.return_value = Session(
        id=uuid4(),
        user_id=user_id,
        tenant_id=tenant_id,
        token_hash="a" * 64,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    service = create_service(
        session_factory,
        tenant_repository_mock=tenant_repository_mock,
        user_repository_mock=user_repository_mock,
        session_repository_mock=session_repository_mock,
    )

    result = await service.resolve_session(token="valid-token")

    assert result is not None
    assert result.user_id == user_id
    assert result.tenant_id == tenant_id


@pytest.mark.anyio
async def test_resolve_session_returns_none_for_missing_token() -> None:
    (
        session_factory,
        tenant_repository_mock,
        user_repository_mock,
        session_repository_mock,
    ) = create_test_dependencies()
    session_repository_mock.get_by_token_hash.return_value = None
    service = create_service(
        session_factory,
        tenant_repository_mock=tenant_repository_mock,
        user_repository_mock=user_repository_mock,
        session_repository_mock=session_repository_mock,
    )

    result = await service.resolve_session(token="unknown-token")

    assert result is None


@pytest.mark.anyio
async def test_resolve_session_returns_none_for_revoked_session() -> None:
    (
        session_factory,
        tenant_repository_mock,
        user_repository_mock,
        session_repository_mock,
    ) = create_test_dependencies()
    session_repository_mock.get_by_token_hash.return_value = Session(
        id=uuid4(),
        user_id=uuid4(),
        tenant_id=uuid4(),
        token_hash="b" * 64,
        expires_at=datetime.now(UTC) + timedelta(days=1),
        revoked_at=datetime.now(UTC),
    )
    service = create_service(
        session_factory,
        tenant_repository_mock=tenant_repository_mock,
        user_repository_mock=user_repository_mock,
        session_repository_mock=session_repository_mock,
    )

    result = await service.resolve_session(token="revoked-token")

    assert result is None


@pytest.mark.anyio
async def test_resolve_session_returns_none_for_expired_session() -> None:
    (
        session_factory,
        tenant_repository_mock,
        user_repository_mock,
        session_repository_mock,
    ) = create_test_dependencies()
    session_repository_mock.get_by_token_hash.return_value = Session(
        id=uuid4(),
        user_id=uuid4(),
        tenant_id=uuid4(),
        token_hash="c" * 64,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    service = create_service(
        session_factory,
        tenant_repository_mock=tenant_repository_mock,
        user_repository_mock=user_repository_mock,
        session_repository_mock=session_repository_mock,
    )

    result = await service.resolve_session(token="expired-token")

    assert result is None


@pytest.mark.anyio
async def test_get_profile_returns_identity() -> None:
    (
        session_factory,
        tenant_repository_mock,
        user_repository_mock,
        session_repository_mock,
    ) = create_test_dependencies()
    tenant = create_tenant()
    user = create_user(
        tenant_id=tenant.id,
        password="correct-horse-battery",
    )
    user_repository_mock.get.return_value = user
    tenant_repository_mock.get.return_value = tenant
    service = create_service(
        session_factory,
        tenant_repository_mock=tenant_repository_mock,
        user_repository_mock=user_repository_mock,
        session_repository_mock=session_repository_mock,
    )

    result = await service.get_profile(
        user_id=user.id,
        tenant_id=tenant.id,
    )

    assert result is not None
    assert result.user is user
    assert result.tenant is tenant


@pytest.mark.anyio
async def test_get_profile_returns_none_for_mismatched_tenant() -> None:
    (
        session_factory,
        tenant_repository_mock,
        user_repository_mock,
        session_repository_mock,
    ) = create_test_dependencies()
    user = create_user(
        tenant_id=uuid4(),
        password="correct-horse-battery",
    )
    user_repository_mock.get.return_value = user
    service = create_service(
        session_factory,
        tenant_repository_mock=tenant_repository_mock,
        user_repository_mock=user_repository_mock,
        session_repository_mock=session_repository_mock,
    )

    result = await service.get_profile(
        user_id=user.id,
        tenant_id=uuid4(),
    )

    assert result is None
    tenant_repository_mock.get.assert_not_awaited()


@pytest.mark.anyio
async def test_update_display_name_renames_the_caller() -> None:
    (
        session_factory,
        tenant_repository_mock,
        user_repository_mock,
        session_repository_mock,
    ) = create_test_dependencies()
    tenant = create_tenant()
    existing_user = create_user(
        tenant_id=tenant.id,
        password="correct-horse-battery",
    )
    renamed_user = create_user(
        tenant_id=tenant.id,
        password="correct-horse-battery",
    )
    renamed_user.id = existing_user.id
    renamed_user.display_name = "New Name"
    user_repository_mock.get.return_value = existing_user
    user_repository_mock.update_display_name.return_value = renamed_user
    tenant_repository_mock.get.return_value = tenant
    service = create_service(
        session_factory,
        tenant_repository_mock=tenant_repository_mock,
        user_repository_mock=user_repository_mock,
        session_repository_mock=session_repository_mock,
    )

    result = await service.update_display_name(
        user_id=existing_user.id,
        tenant_id=tenant.id,
        display_name="New Name",
    )

    assert result is not None
    assert result.user.display_name == "New Name"
    user_repository_mock.update_display_name.assert_awaited_once_with(
        user_id=existing_user.id,
        display_name="New Name",
    )


@pytest.mark.anyio
async def test_update_display_name_returns_none_for_mismatched_tenant() -> None:
    (
        session_factory,
        tenant_repository_mock,
        user_repository_mock,
        session_repository_mock,
    ) = create_test_dependencies()
    user = create_user(
        tenant_id=uuid4(),
        password="correct-horse-battery",
    )
    user_repository_mock.get.return_value = user
    service = create_service(
        session_factory,
        tenant_repository_mock=tenant_repository_mock,
        user_repository_mock=user_repository_mock,
        session_repository_mock=session_repository_mock,
    )

    result = await service.update_display_name(
        user_id=user.id,
        tenant_id=uuid4(),
        display_name="New Name",
    )

    assert result is None
    user_repository_mock.update_display_name.assert_not_awaited()


@pytest.mark.anyio
async def test_change_password_succeeds_with_correct_current_password() -> None:
    (
        session_factory,
        tenant_repository_mock,
        user_repository_mock,
        session_repository_mock,
    ) = create_test_dependencies()
    tenant = create_tenant()
    user = create_user(
        tenant_id=tenant.id,
        password="correct-horse-battery",
    )
    user_repository_mock.get.return_value = user
    service = create_service(
        session_factory,
        tenant_repository_mock=tenant_repository_mock,
        user_repository_mock=user_repository_mock,
        session_repository_mock=session_repository_mock,
    )

    await service.change_password(
        user_id=user.id,
        tenant_id=tenant.id,
        current_password="correct-horse-battery",
        new_password="new-correct-horse-battery",
    )

    user_repository_mock.update_password_hash.assert_awaited_once()
    assert (
        user_repository_mock.update_password_hash.await_args.kwargs["password_hash"]
        != user.password_hash
    )


@pytest.mark.anyio
async def test_change_password_rejects_wrong_current_password() -> None:
    (
        session_factory,
        tenant_repository_mock,
        user_repository_mock,
        session_repository_mock,
    ) = create_test_dependencies()
    tenant = create_tenant()
    user = create_user(
        tenant_id=tenant.id,
        password="correct-horse-battery",
    )
    user_repository_mock.get.return_value = user
    service = create_service(
        session_factory,
        tenant_repository_mock=tenant_repository_mock,
        user_repository_mock=user_repository_mock,
        session_repository_mock=session_repository_mock,
    )

    with pytest.raises(InvalidCredentialsError):
        await service.change_password(
            user_id=user.id,
            tenant_id=tenant.id,
            current_password="wrong-password",
            new_password="new-correct-horse-battery",
        )

    user_repository_mock.update_password_hash.assert_not_awaited()


@pytest.mark.anyio
async def test_change_password_rejects_mismatched_tenant() -> None:
    (
        session_factory,
        tenant_repository_mock,
        user_repository_mock,
        session_repository_mock,
    ) = create_test_dependencies()
    user = create_user(
        tenant_id=uuid4(),
        password="correct-horse-battery",
    )
    user_repository_mock.get.return_value = user
    service = create_service(
        session_factory,
        tenant_repository_mock=tenant_repository_mock,
        user_repository_mock=user_repository_mock,
        session_repository_mock=session_repository_mock,
    )

    with pytest.raises(InvalidCredentialsError):
        await service.change_password(
            user_id=user.id,
            tenant_id=uuid4(),
            current_password="correct-horse-battery",
            new_password="new-correct-horse-battery",
        )

    user_repository_mock.update_password_hash.assert_not_awaited()
