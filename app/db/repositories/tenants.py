from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Tenant, User


def _normalize_required(
    value: str,
    *,
    field_name: str,
    max_length: int,
) -> str:
    normalized = value.strip()

    if not normalized:
        raise ValueError(f"{field_name} must not be empty.")

    if len(normalized) > max_length:
        raise ValueError(f"{field_name} must not exceed {max_length} characters.")

    return normalized


class TenantRepository:
    """Persist and retrieve enterprise tenants."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def create(
        self,
        *,
        slug: str,
        name: str,
    ) -> Tenant:
        """Create a tenant without committing its transaction."""

        tenant = Tenant(
            slug=_normalize_required(
                slug,
                field_name="slug",
                max_length=100,
            ).lower(),
            name=_normalize_required(
                name,
                field_name="name",
                max_length=200,
            ),
        )

        self._session.add(tenant)
        await self._session.flush()

        return tenant


class UserRepository:
    """Persist users within an enterprise tenant."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        email: str,
        password_hash: str,
        display_name: str | None = None,
    ) -> User:
        """Create a tenant user without committing its transaction."""

        normalized_email = _normalize_required(
            email,
            field_name="email",
            max_length=320,
        ).lower()

        normalized_display_name = display_name.strip() if display_name is not None else None

        if normalized_display_name == "":
            normalized_display_name = None

        if normalized_display_name is not None and len(normalized_display_name) > 200:
            raise ValueError("display_name must not exceed 200 characters.")

        user = User(
            tenant_id=tenant_id,
            email=normalized_email,
            password_hash=password_hash,
            display_name=normalized_display_name,
        )

        self._session.add(user)
        await self._session.flush()

        return user

    async def get_by_email(
        self,
        *,
        email: str,
    ) -> User | None:
        """Return the user with this email, if any."""

        normalized_email = email.strip().lower()

        statement = select(User).where(User.email == normalized_email)

        result = await self._session.scalar(statement)

        return result
