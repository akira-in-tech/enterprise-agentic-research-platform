from dataclasses import dataclass
from uuid import UUID, uuid4

from app.core.config import settings
from app.services.cache.base import AtomicLockClient
from app.services.cache.keys import (
    create_research_idempotency_lock_redis_key,
)


@dataclass(frozen=True)
class ResearchIdempotencyLockLease:
    """Proof that one process currently owns an idempotency lock."""

    redis_key: str
    owner_token: str


class RedisResearchIdempotencyLockManager:
    """Coordinate tenant-scoped idempotent research execution."""

    def __init__(
        self,
        client: AtomicLockClient,
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        selected_ttl = (
            ttl_seconds
            if ttl_seconds is not None
            else settings.redis_research_idempotency_lock_ttl_seconds
        )

        if selected_ttl < 1:
            raise ValueError("Research idempotency lock ttl_seconds must be at least 1.")

        self._client = client
        self._ttl_seconds = selected_ttl

    async def acquire(
        self,
        *,
        tenant_id: UUID,
        client_key: str,
    ) -> ResearchIdempotencyLockLease | None:
        """Acquire a lock or return None when another owner holds it."""

        redis_key = create_research_idempotency_lock_redis_key(
            tenant_id=tenant_id,
            client_key=client_key,
        )
        owner_token = uuid4().hex

        acquired = await self._client.set_if_absent(
            key=redis_key,
            value=owner_token,
            ttl_seconds=self._ttl_seconds,
        )

        if not acquired:
            return None

        return ResearchIdempotencyLockLease(
            redis_key=redis_key,
            owner_token=owner_token,
        )

    async def release(
        self,
        lease: ResearchIdempotencyLockLease,
    ) -> bool:
        """Release a lock only when the lease still owns it."""

        return await self._client.delete_if_value(
            key=lease.redis_key,
            expected_value=lease.owner_token,
        )

    async def renew(
        self,
        lease: ResearchIdempotencyLockLease,
    ) -> bool:
        """Extend a lock's TTL only when the lease still owns it."""

        return await self._client.extend_if_value(
            key=lease.redis_key,
            expected_value=lease.owner_token,
            ttl_seconds=self._ttl_seconds,
        )
