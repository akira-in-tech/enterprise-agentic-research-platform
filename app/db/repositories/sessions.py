from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Session


class SessionRepository:
    """Persist and resolve durable login sessions."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: UUID,
        tenant_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> Session:
        """Create a login session without committing its transaction."""

        record = Session(
            id=uuid4(),
            user_id=user_id,
            tenant_id=tenant_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )

        self._session.add(record)
        await self._session.flush()

        return record

    async def get_by_token_hash(
        self,
        *,
        token_hash: str,
    ) -> Session | None:
        """Return the session matching a hashed token, if any."""

        statement = select(Session).where(Session.token_hash == token_hash)

        result = await self._session.scalar(statement)

        return result

    async def revoke(
        self,
        *,
        token_hash: str,
        revoked_at: datetime,
    ) -> None:
        """Mark a session revoked without committing its transaction."""

        record = await self.get_by_token_hash(token_hash=token_hash)

        if record is None:
            return

        record.revoked_at = revoked_at
        await self._session.flush()
