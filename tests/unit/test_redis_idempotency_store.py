from uuid import uuid4

import pytest

from app.schemas.idempotency import ResearchIdempotencyRecord
from app.schemas.research import CreateResearchRunResponse
from app.services.cache import (
    RedisResearchIdempotencyStore,
    create_research_idempotency_redis_key,
    create_research_request_fingerprint,
)


class RecordingTextCacheClient:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.get_calls: list[str] = []
        self.set_calls: list[tuple[str, str, int]] = []
        self.delete_calls: list[str] = []

    async def get_text(
        self,
        *,
        key: str,
    ) -> str | None:
        self.get_calls.append(key)

        return self.values.get(key)

    async def set_text(
        self,
        *,
        key: str,
        value: str,
        ttl_seconds: int,
    ) -> None:
        self.set_calls.append(
            (
                key,
                value,
                ttl_seconds,
            )
        )
        self.values[key] = value

    async def delete(
        self,
        *,
        key: str,
    ) -> bool:
        self.delete_calls.append(key)

        return (
            self.values.pop(
                key,
                None,
            )
            is not None
        )


def create_test_record() -> ResearchIdempotencyRecord:
    return ResearchIdempotencyRecord(
        request_fingerprint=(
            create_research_request_fingerprint(
                query="What is a mutex?",
                llm_provider="ollama",
                requested_by_user_id=None,
            )
        ),
        response=CreateResearchRunResponse(
            research_run_id=uuid4(),
            llm_provider="ollama",
            status="completed",
            cache_hit=False,
            workflow_status="direct_answer_completed",
            route="direct",
            answer="A mutex protects a critical section.",
        ),
    )


@pytest.mark.anyio
async def test_get_returns_none_for_idempotency_miss() -> None:
    client = RecordingTextCacheClient()
    store = RedisResearchIdempotencyStore(
        client,
        ttl_seconds=86_400,
    )
    tenant_id = uuid4()

    result = await store.get(
        tenant_id=tenant_id,
        client_key="request-123",
    )

    assert result is None
    assert client.get_calls == [
        create_research_idempotency_redis_key(
            tenant_id=tenant_id,
            client_key="request-123",
        )
    ]


@pytest.mark.anyio
async def test_set_serializes_idempotency_record_with_ttl() -> None:
    client = RecordingTextCacheClient()
    store = RedisResearchIdempotencyStore(
        client,
        ttl_seconds=43_200,
    )
    tenant_id = uuid4()
    record = create_test_record()

    await store.set(
        tenant_id=tenant_id,
        client_key="request-123",
        record=record,
    )

    assert len(client.set_calls) == 1

    stored_key, stored_payload, stored_ttl = client.set_calls[0]

    assert stored_key == create_research_idempotency_redis_key(
        tenant_id=tenant_id,
        client_key="request-123",
    )
    assert stored_ttl == 43_200
    assert (
        ResearchIdempotencyRecord.model_validate_json(
            stored_payload,
        )
        == record
    )


@pytest.mark.anyio
async def test_get_restores_idempotency_record() -> None:
    client = RecordingTextCacheClient()
    store = RedisResearchIdempotencyStore(
        client,
        ttl_seconds=86_400,
    )
    tenant_id = uuid4()
    record = create_test_record()

    await store.set(
        tenant_id=tenant_id,
        client_key="request-123",
        record=record,
    )

    restored_record = await store.get(
        tenant_id=tenant_id,
        client_key="request-123",
    )

    assert restored_record == record


@pytest.mark.anyio
async def test_idempotency_store_isolates_tenants() -> None:
    client = RecordingTextCacheClient()
    store = RedisResearchIdempotencyStore(
        client,
        ttl_seconds=86_400,
    )
    tenant_a = uuid4()
    tenant_b = uuid4()

    await store.set(
        tenant_id=tenant_a,
        client_key="request-123",
        record=create_test_record(),
    )

    tenant_b_record = await store.get(
        tenant_id=tenant_b,
        client_key="request-123",
    )

    assert tenant_b_record is None


@pytest.mark.anyio
async def test_get_deletes_malformed_idempotency_record() -> None:
    client = RecordingTextCacheClient()
    store = RedisResearchIdempotencyStore(
        client,
        ttl_seconds=86_400,
    )
    tenant_id = uuid4()
    redis_key = create_research_idempotency_redis_key(
        tenant_id=tenant_id,
        client_key="request-123",
    )
    client.values[redis_key] = "not-valid-json"

    result = await store.get(
        tenant_id=tenant_id,
        client_key="request-123",
    )

    assert result is None
    assert redis_key not in client.values
    assert client.delete_calls == [
        redis_key,
    ]


@pytest.mark.anyio
async def test_delete_removes_idempotency_record() -> None:
    client = RecordingTextCacheClient()
    store = RedisResearchIdempotencyStore(
        client,
        ttl_seconds=86_400,
    )
    tenant_id = uuid4()

    await store.set(
        tenant_id=tenant_id,
        client_key="request-123",
        record=create_test_record(),
    )

    first_delete = await store.delete(
        tenant_id=tenant_id,
        client_key="request-123",
    )
    second_delete = await store.delete(
        tenant_id=tenant_id,
        client_key="request-123",
    )

    assert first_delete is True
    assert second_delete is False


def test_idempotency_store_rejects_non_positive_ttl() -> None:
    with pytest.raises(
        ValueError,
        match="ttl_seconds must be at least 1",
    ):
        RedisResearchIdempotencyStore(
            RecordingTextCacheClient(),
            ttl_seconds=0,
        )
