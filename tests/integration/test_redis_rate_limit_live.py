import asyncio
from uuid import uuid4

import pytest

from app.core.config import settings
from app.services.cache import (
    RedisConnection,
    RedisResearchRateLimiter,
    create_research_rate_limit_redis_key,
)


@pytest.mark.integration
@pytest.mark.anyio
async def test_live_redis_enforces_atomic_tenant_rate_limit() -> None:
    """Verify concurrent allowance, tenant isolation, TTL and cleanup."""

    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    connection = RedisConnection.from_url()
    limiter = RedisResearchRateLimiter(
        connection,
        request_limit=3,
        window_seconds=60,
    )
    tenant_a = uuid4()
    tenant_b = uuid4()
    tenant_a_key = create_research_rate_limit_redis_key(
        tenant_id=tenant_a,
    )
    tenant_b_key = create_research_rate_limit_redis_key(
        tenant_id=tenant_b,
    )

    try:
        await connection.delete(
            key=tenant_a_key,
        )
        await connection.delete(
            key=tenant_b_key,
        )

        tenant_a_decisions = await asyncio.gather(
            *(
                limiter.check(
                    tenant_id=tenant_a,
                )
                for _ in range(5)
            )
        )
        tenant_b_decision = await limiter.check(
            tenant_id=tenant_b,
        )

        assert sum(decision.allowed for decision in tenant_a_decisions) == 3
        assert sum(not decision.allowed for decision in tenant_a_decisions) == 2
        assert tenant_b_decision.allowed is True
        assert tenant_b_decision.remaining == 2

        remaining_ttl = await connection.ttl_seconds(
            key=tenant_a_key,
        )

        assert 0 < remaining_ttl <= 60

    finally:
        try:
            await connection.delete(
                key=tenant_a_key,
            )
            await connection.delete(
                key=tenant_b_key,
            )
        finally:
            await connection.close()
