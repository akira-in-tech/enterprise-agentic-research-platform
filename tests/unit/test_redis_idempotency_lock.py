from uuid import UUID, uuid4

import pytest

from app.services.cache import (
    RedisResearchIdempotencyLockManager,
    create_research_idempotency_lock_redis_key,
)


class RecordingAtomicLockClient:
    def __init__(
        self,
        *,
        acquire_result: bool = True,
        release_result: bool = True,
    ) -> None:
        self.acquire_result = acquire_result
        self.release_result = release_result
        self.set_calls: list[tuple[str, str, int]] = []
        self.delete_calls: list[tuple[str, str]] = []

    async def set_if_absent(
        self,
        *,
        key: str,
        value: str,
        ttl_seconds: int,
    ) -> bool:
        self.set_calls.append(
            (
                key,
                value,
                ttl_seconds,
            )
        )

        return self.acquire_result

    async def delete_if_value(
        self,
        *,
        key: str,
        expected_value: str,
    ) -> bool:
        self.delete_calls.append(
            (
                key,
                expected_value,
            )
        )

        return self.release_result


@pytest.mark.anyio
async def test_acquire_returns_unique_lock_lease() -> None:
    client = RecordingAtomicLockClient()
    manager = RedisResearchIdempotencyLockManager(
        client,
        ttl_seconds=120,
    )
    tenant_id = uuid4()

    lease = await manager.acquire(
        tenant_id=tenant_id,
        client_key="request-123",
    )

    assert lease is not None
    assert lease.redis_key == create_research_idempotency_lock_redis_key(
        tenant_id=tenant_id,
        client_key="request-123",
    )
    assert (
        UUID(
            hex=lease.owner_token,
        ).version
        == 4
    )
    assert client.set_calls == [
        (
            lease.redis_key,
            lease.owner_token,
            120,
        )
    ]


@pytest.mark.anyio
async def test_acquire_returns_none_when_lock_is_held() -> None:
    client = RecordingAtomicLockClient(
        acquire_result=False,
    )
    manager = RedisResearchIdempotencyLockManager(
        client,
        ttl_seconds=120,
    )

    lease = await manager.acquire(
        tenant_id=uuid4(),
        client_key="request-123",
    )

    assert lease is None
    assert len(client.set_calls) == 1


@pytest.mark.anyio
async def test_release_uses_lease_owner_token() -> None:
    client = RecordingAtomicLockClient()
    manager = RedisResearchIdempotencyLockManager(
        client,
        ttl_seconds=120,
    )

    lease = await manager.acquire(
        tenant_id=uuid4(),
        client_key="request-123",
    )

    assert lease is not None

    released = await manager.release(
        lease,
    )

    assert released is True
    assert client.delete_calls == [
        (
            lease.redis_key,
            lease.owner_token,
        )
    ]


@pytest.mark.anyio
async def test_release_preserves_lock_when_lease_is_stale() -> None:
    client = RecordingAtomicLockClient(
        release_result=False,
    )
    manager = RedisResearchIdempotencyLockManager(
        client,
        ttl_seconds=120,
    )

    lease = await manager.acquire(
        tenant_id=uuid4(),
        client_key="request-123",
    )

    assert lease is not None
    assert (
        await manager.release(
            lease,
        )
        is False
    )


def test_lock_manager_rejects_non_positive_ttl() -> None:
    with pytest.raises(
        ValueError,
        match="lock ttl_seconds must be at least 1",
    ):
        RedisResearchIdempotencyLockManager(
            RecordingAtomicLockClient(),
            ttl_seconds=0,
        )
