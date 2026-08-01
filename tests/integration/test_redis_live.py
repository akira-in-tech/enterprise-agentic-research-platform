from uuid import uuid4

import pytest

from app.core.config import settings
from app.services.cache import (
    RedisConnection,
    RedisResearchIdempotencyLockManager,
    create_research_idempotency_lock_redis_key,
)


@pytest.mark.integration
@pytest.mark.anyio
async def test_redis_live_connection_round_trip() -> None:
    """Verify the real Redis connection pool and health check."""

    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    connection = RedisConnection.from_url()

    try:
        assert await connection.ping() is True
        assert await connection.ping() is True
    finally:
        await connection.close()


@pytest.mark.integration
@pytest.mark.anyio
async def test_redis_live_atomic_lock_round_trip() -> None:
    """Verify atomic acquisition and token-checked release in real Redis."""

    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    connection = RedisConnection.from_url()
    lock_key = create_research_idempotency_lock_redis_key(
        tenant_id=uuid4(),
        client_key="live-atomic-lock-request",
    )
    owner_token = uuid4().hex
    competing_token = uuid4().hex

    try:
        await connection.delete(
            key=lock_key,
        )

        first_acquire = await connection.set_if_absent(
            key=lock_key,
            value=owner_token,
            ttl_seconds=60,
        )
        competing_acquire = await connection.set_if_absent(
            key=lock_key,
            value=competing_token,
            ttl_seconds=60,
        )

        assert first_acquire is True
        assert competing_acquire is False
        assert (
            await connection.get_text(
                key=lock_key,
            )
            == owner_token
        )

        wrong_owner_release = await connection.delete_if_value(
            key=lock_key,
            expected_value=competing_token,
        )

        assert wrong_owner_release is False
        assert (
            await connection.get_text(
                key=lock_key,
            )
            == owner_token
        )

        correct_owner_release = await connection.delete_if_value(
            key=lock_key,
            expected_value=owner_token,
        )

        assert correct_owner_release is True
        assert (
            await connection.get_text(
                key=lock_key,
            )
            is None
        )

    finally:
        try:
            await connection.delete(
                key=lock_key,
            )
        finally:
            await connection.close()


@pytest.mark.integration
@pytest.mark.anyio
async def test_redis_live_idempotency_lock_manager() -> None:
    """Verify lock leases, contention, TTL and cleanup in real Redis."""

    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    connection = RedisConnection.from_url()
    manager = RedisResearchIdempotencyLockManager(
        connection,
        ttl_seconds=60,
    )
    tenant_id = uuid4()
    client_key = "live-lock-manager-request"
    redis_key = create_research_idempotency_lock_redis_key(
        tenant_id=tenant_id,
        client_key=client_key,
    )

    try:
        await connection.delete(
            key=redis_key,
        )

        lease = await manager.acquire(
            tenant_id=tenant_id,
            client_key=client_key,
        )

        assert lease is not None
        assert lease.redis_key == redis_key
        assert (
            await connection.get_text(
                key=redis_key,
            )
            == lease.owner_token
        )

        remaining_ttl = await connection.ttl_seconds(
            key=redis_key,
        )

        assert 0 < remaining_ttl <= 60

        competing_lease = await manager.acquire(
            tenant_id=tenant_id,
            client_key=client_key,
        )

        assert competing_lease is None

        released = await manager.release(
            lease,
        )

        assert released is True
        assert (
            await connection.get_text(
                key=redis_key,
            )
            is None
        )

    finally:
        try:
            await connection.delete(
                key=redis_key,
            )
        finally:
            await connection.close()
