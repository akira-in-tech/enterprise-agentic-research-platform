from uuid import uuid4

import pytest

from app.core.config import settings
from app.schemas.idempotency import ResearchIdempotencyRecord
from app.schemas.research import CreateResearchRunResponse
from app.services.cache import (
    RedisConnection,
    RedisResearchIdempotencyStore,
    create_research_idempotency_redis_key,
    create_research_request_fingerprint,
)


@pytest.mark.integration
@pytest.mark.anyio
async def test_redis_idempotency_store_live_round_trip() -> None:
    """Verify JSON, TTL, tenant isolation and cleanup in real Redis."""

    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    connection = RedisConnection.from_url()
    store = RedisResearchIdempotencyStore(
        connection,
        ttl_seconds=60,
    )
    tenant_a = uuid4()
    tenant_b = uuid4()
    user_id = uuid4()
    client_key = "live-idempotency-request-123"
    query = "Explain idempotency in REST APIs."
    redis_key = create_research_idempotency_redis_key(
        tenant_id=tenant_a,
        client_key=client_key,
    )
    expected_record = ResearchIdempotencyRecord(
        request_fingerprint=(
            create_research_request_fingerprint(
                query=query,
                llm_provider="ollama",
                requested_by_user_id=user_id,
            )
        ),
        response=CreateResearchRunResponse(
            research_run_id=uuid4(),
            llm_provider="ollama",
            status="completed",
            cache_hit=False,
            workflow_status="direct_answer_completed",
            route="direct",
            route_reason=("The question uses stable engineering knowledge."),
            answer=(
                "An idempotency key allows repeated equivalent "
                "requests to reuse one completed operation."
            ),
        ),
    )

    try:
        await connection.delete(
            key=redis_key,
        )

        initial_record = await store.get(
            tenant_id=tenant_a,
            client_key=client_key,
        )

        assert initial_record is None

        await store.set(
            tenant_id=tenant_a,
            client_key=client_key,
            record=expected_record,
        )

        restored_record = await store.get(
            tenant_id=tenant_a,
            client_key=client_key,
        )
        tenant_b_record = await store.get(
            tenant_id=tenant_b,
            client_key=client_key,
        )

        assert restored_record == expected_record
        assert tenant_b_record is None

        remaining_ttl = await connection.ttl_seconds(
            key=redis_key,
        )

        assert 0 < remaining_ttl <= 60

        first_delete = await store.delete(
            tenant_id=tenant_a,
            client_key=client_key,
        )
        second_delete = await store.delete(
            tenant_id=tenant_a,
            client_key=client_key,
        )
        record_after_delete = await store.get(
            tenant_id=tenant_a,
            client_key=client_key,
        )

        assert first_delete is True
        assert second_delete is False
        assert record_after_delete is None

    finally:
        try:
            await connection.delete(
                key=redis_key,
            )
        finally:
            await connection.close()
