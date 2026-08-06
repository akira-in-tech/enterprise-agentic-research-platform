import hashlib
import re
import secrets
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Tenant, User
from app.db.repositories import SessionRepository, TenantRepository, UserRepository
from app.services.auth.passwords import hash_password, verify_password

DEFAULT_SESSION_TTL_SECONDS = 60 * 60 * 24 * 7

_SLUG_DISALLOWED_PATTERN = re.compile(r"[^a-z0-9]+")

# Hashed once at import so a login attempt for an unknown email still pays the
# same Argon2 cost as a real one, keeping response timing from revealing
# whether the address is registered.
_DUMMY_PASSWORD_HASH = hash_password("not-a-real-password-timing-guard")


class TransactionalSessionFactory(Protocol):
    """Create a session with an automatically managed transaction."""

    def begin(
        self,
    ) -> AbstractAsyncContextManager[AsyncSession]:
        """Open one short database transaction."""


TenantRepositoryFactory = Callable[[AsyncSession], TenantRepository]
UserRepositoryFactory = Callable[[AsyncSession], UserRepository]
SessionRepositoryFactory = Callable[[AsyncSession], SessionRepository]


class EmailAlreadyRegisteredError(RuntimeError):
    """Indicate that a registration email is already in use."""


class InvalidCredentialsError(RuntimeError):
    """Indicate that login credentials did not match a known account."""


@dataclass(frozen=True)
class ResolvedSession:
    """Identify the tenant user behind a valid session token."""

    user_id: UUID
    tenant_id: UUID


@dataclass(frozen=True)
class AuthenticatedIdentity:
    """Carry the tenant user and tenant behind a session."""

    user: User
    tenant: Tenant


@dataclass(frozen=True)
class AuthenticatedSession:
    """Carry a newly issued session alongside the identity it belongs to."""

    identity: AuthenticatedIdentity
    token: str
    expires_at: datetime


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _generate_tenant_slug(name: str) -> str:
    """Build a URL-safe tenant slug from a display name.

    Always appends a short random suffix rather than checking for
    collisions first: self-service signups always create a brand-new
    tenant, the slug is not shown to users anywhere yet, and this keeps
    registration a single pre-check (email) instead of a retry loop.
    """

    base = _SLUG_DISALLOWED_PATTERN.sub("-", name.strip().lower()).strip("-")[:80]
    suffix = uuid4().hex[:8]

    return f"{base}-{suffix}" if base else f"tenant-{suffix}"


class AuthService:
    """Register, authenticate, and resolve durable tenant-user sessions."""

    def __init__(
        self,
        session_factory: TransactionalSessionFactory,
        *,
        tenant_repository_factory: TenantRepositoryFactory = TenantRepository,
        user_repository_factory: UserRepositoryFactory = UserRepository,
        session_repository_factory: SessionRepositoryFactory = SessionRepository,
        session_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
    ) -> None:
        self._session_factory = session_factory
        self._tenant_repository_factory = tenant_repository_factory
        self._user_repository_factory = user_repository_factory
        self._session_repository_factory = session_repository_factory
        self._session_ttl_seconds = session_ttl_seconds

    async def register(
        self,
        *,
        email: str,
        password: str,
        tenant_name: str,
        display_name: str | None = None,
    ) -> AuthenticatedSession:
        """Create a new tenant and its first user, then issue a session."""

        async with self._session_factory.begin() as session:
            user_repository = self._user_repository_factory(session)

            existing_user = await user_repository.get_by_email(email=email)

            if existing_user is not None:
                raise EmailAlreadyRegisteredError("Email is already registered.")

            tenant_repository = self._tenant_repository_factory(session)
            tenant = await tenant_repository.create(
                slug=_generate_tenant_slug(tenant_name),
                name=tenant_name,
            )
            user = await user_repository.create(
                tenant_id=tenant.id,
                email=email,
                password_hash=hash_password(password),
                display_name=display_name,
            )

            return await self._issue_session(
                session,
                user=user,
                tenant=tenant,
            )

    async def login(
        self,
        *,
        email: str,
        password: str,
    ) -> AuthenticatedSession:
        """Authenticate a user by email and password and issue a session."""

        async with self._session_factory.begin() as session:
            user_repository = self._user_repository_factory(session)
            user = await user_repository.get_by_email(email=email)

            if user is None:
                verify_password(password, _DUMMY_PASSWORD_HASH)
                raise InvalidCredentialsError("Invalid email or password.")

            if not verify_password(password, user.password_hash):
                raise InvalidCredentialsError("Invalid email or password.")

            tenant_repository = self._tenant_repository_factory(session)
            tenant = await tenant_repository.get(tenant_id=user.tenant_id)

            if tenant is None:
                raise InvalidCredentialsError("Invalid email or password.")

            return await self._issue_session(
                session,
                user=user,
                tenant=tenant,
            )

    async def logout(
        self,
        *,
        token: str,
    ) -> None:
        """Revoke a session so it can no longer authenticate requests."""

        async with self._session_factory.begin() as session:
            session_repository = self._session_repository_factory(session)
            await session_repository.revoke(
                token_hash=_hash_token(token),
                revoked_at=datetime.now(UTC),
            )

    async def resolve_session(
        self,
        *,
        token: str,
    ) -> ResolvedSession | None:
        """Return the tenant user behind a session token, if it is valid."""

        async with self._session_factory.begin() as session:
            session_repository = self._session_repository_factory(session)
            record = await session_repository.get_by_token_hash(
                token_hash=_hash_token(token),
            )

            if record is None:
                return None

            if record.revoked_at is not None:
                return None

            if record.expires_at <= datetime.now(UTC):
                return None

            return ResolvedSession(
                user_id=record.user_id,
                tenant_id=record.tenant_id,
            )

    async def get_profile(
        self,
        *,
        user_id: UUID,
        tenant_id: UUID,
    ) -> AuthenticatedIdentity | None:
        """Return the user and tenant behind an already-resolved session."""

        async with self._session_factory.begin() as session:
            user = await self._user_repository_factory(session).get(user_id=user_id)

            if user is None or user.tenant_id != tenant_id:
                return None

            tenant = await self._tenant_repository_factory(session).get(tenant_id=tenant_id)

            if tenant is None:
                return None

            return AuthenticatedIdentity(
                user=user,
                tenant=tenant,
            )

    async def _issue_session(
        self,
        session: AsyncSession,
        *,
        user: User,
        tenant: Tenant,
    ) -> AuthenticatedSession:
        """Create and persist a new session for an already-flushed user."""

        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(seconds=self._session_ttl_seconds)

        session_repository = self._session_repository_factory(session)
        await session_repository.create(
            user_id=user.id,
            tenant_id=tenant.id,
            token_hash=_hash_token(token),
            expires_at=expires_at,
        )

        return AuthenticatedSession(
            identity=AuthenticatedIdentity(
                user=user,
                tenant=tenant,
            ),
            token=token,
            expires_at=expires_at,
        )
