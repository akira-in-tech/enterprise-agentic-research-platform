from uuid import uuid4

import pytest

from app.core.config import settings
from app.schemas.cache import CachedResearchResult
from app.services.cache import (
    RedisConnection,
    RedisResearchResultCache,
    create_research_result_cache_key,
)


@pytest.mark.integration
@pytest.mark.anyio
async def test_redis_research_result_cache_live_round_trip() -> None:
    """Verify JSON, TTL, tenant isolation and cleanup against real Redis."""

    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    connection = RedisConnection.from_url()
    cache = RedisResearchResultCache(
        connection,
        ttl_seconds=60,
    )
    tenant_a = uuid4()
    tenant_b = uuid4()
    query = "Explain DNS recursive resolution."
    cache_key = create_research_result_cache_key(
        tenant_id=tenant_a,
        llm_provider="ollama",
        query=query,
    )
    expected_result = CachedResearchResult(
        llm_provider="ollama",
        workflow_status="direct_answer_completed",
        route="direct",
        route_reason=("The question can be answered using stable knowledge."),
        answer=(
            "A recursive DNS resolver queries authoritative name servers on behalf of the client."
        ),
    )

    try:
        initial_result = await cache.get(
            tenant_id=tenant_a,
            llm_provider="ollama",
            query=query,
        )

        assert initial_result is None

        await cache.set(
            tenant_id=tenant_a,
            query=query,
            result=expected_result,
        )

        restored_result = await cache.get(
            tenant_id=tenant_a,
            llm_provider="ollama",
            query=query,
        )

        assert restored_result == expected_result

        tenant_b_result = await cache.get(
            tenant_id=tenant_b,
            llm_provider="ollama",
            query=query,
        )
        anthropic_result = await cache.get(
            tenant_id=tenant_a,
            llm_provider="anthropic",
            query=query,
        )

        assert tenant_b_result is None
        assert anthropic_result is None

        remaining_ttl = await connection.ttl_seconds(
            key=cache_key,
        )

        assert 0 < remaining_ttl <= 60

        deleted = await cache.delete(
            tenant_id=tenant_a,
            llm_provider="ollama",
            query=query,
        )
        result_after_delete = await cache.get(
            tenant_id=tenant_a,
            llm_provider="ollama",
            query=query,
        )

        assert deleted is True
        assert result_after_delete is None

    finally:
        try:
            await connection.delete(
                key=cache_key,
            )
        finally:
            await connection.close()
