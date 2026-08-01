from uuid import uuid4

import pytest

from app.schemas.cache import CachedResearchResult
from app.services.cache.keys import (
    create_research_result_cache_key,
)
from app.services.cache.research_results import (
    RedisResearchResultCache,
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


def create_cached_result(
    *,
    llm_provider: str = "ollama",
) -> CachedResearchResult:
    return CachedResearchResult.model_validate(
        {
            "llm_provider": llm_provider,
            "workflow_status": "direct_answer_completed",
            "route": "direct",
            "route_reason": ("The question can be answered using stable knowledge."),
            "answer": ("epoll is Linux's scalable I/O event notification interface."),
        }
    )


@pytest.mark.anyio
async def test_get_returns_none_for_cache_miss() -> None:
    client = RecordingTextCacheClient()
    cache = RedisResearchResultCache(
        client,
        ttl_seconds=900,
    )
    tenant_id = uuid4()

    result = await cache.get(
        tenant_id=tenant_id,
        llm_provider="ollama",
        query="Explain Linux epoll.",
    )

    assert result is None
    assert client.get_calls == [
        create_research_result_cache_key(
            tenant_id=tenant_id,
            llm_provider="ollama",
            query="Explain Linux epoll.",
        )
    ]


@pytest.mark.anyio
async def test_set_serializes_result_with_ttl() -> None:
    client = RecordingTextCacheClient()
    cache = RedisResearchResultCache(
        client,
        ttl_seconds=1_800,
    )
    tenant_id = uuid4()
    result = create_cached_result()

    await cache.set(
        tenant_id=tenant_id,
        query="Explain Linux epoll.",
        result=result,
    )

    expected_key = create_research_result_cache_key(
        tenant_id=tenant_id,
        llm_provider="ollama",
        query="Explain Linux epoll.",
    )

    assert len(client.set_calls) == 1

    stored_key, stored_payload, stored_ttl = client.set_calls[0]

    assert stored_key == expected_key
    assert stored_ttl == 1_800
    assert (
        CachedResearchResult.model_validate_json(
            stored_payload,
        )
        == result
    )


@pytest.mark.anyio
async def test_get_deserializes_cached_result() -> None:
    client = RecordingTextCacheClient()
    cache = RedisResearchResultCache(
        client,
        ttl_seconds=900,
    )
    tenant_id = uuid4()
    expected_result = create_cached_result()

    await cache.set(
        tenant_id=tenant_id,
        query="What is a mutex?",
        result=expected_result,
    )

    restored_result = await cache.get(
        tenant_id=tenant_id,
        llm_provider="ollama",
        query="What is a mutex?",
    )

    assert restored_result == expected_result


@pytest.mark.anyio
async def test_cache_isolates_tenants() -> None:
    client = RecordingTextCacheClient()
    cache = RedisResearchResultCache(
        client,
        ttl_seconds=900,
    )
    tenant_a = uuid4()
    tenant_b = uuid4()

    await cache.set(
        tenant_id=tenant_a,
        query="Explain DNS recursive resolution.",
        result=create_cached_result(),
    )

    tenant_b_result = await cache.get(
        tenant_id=tenant_b,
        llm_provider="ollama",
        query="Explain DNS recursive resolution.",
    )

    assert tenant_b_result is None


@pytest.mark.anyio
async def test_get_deletes_malformed_payload() -> None:
    client = RecordingTextCacheClient()
    cache = RedisResearchResultCache(
        client,
        ttl_seconds=900,
    )
    tenant_id = uuid4()
    key = create_research_result_cache_key(
        tenant_id=tenant_id,
        llm_provider="ollama",
        query="Explain HTTP keep-alive.",
    )
    client.values[key] = "not-valid-json"

    result = await cache.get(
        tenant_id=tenant_id,
        llm_provider="ollama",
        query="Explain HTTP keep-alive.",
    )

    assert result is None
    assert key not in client.values
    assert client.delete_calls == [
        key,
    ]


@pytest.mark.anyio
async def test_get_deletes_provider_mismatch() -> None:
    client = RecordingTextCacheClient()
    cache = RedisResearchResultCache(
        client,
        ttl_seconds=900,
    )
    tenant_id = uuid4()
    key = create_research_result_cache_key(
        tenant_id=tenant_id,
        llm_provider="ollama",
        query="Explain HTTP/2 multiplexing.",
    )
    mismatched_result = create_cached_result(
        llm_provider="anthropic",
    )
    client.values[key] = mismatched_result.model_dump_json()

    result = await cache.get(
        tenant_id=tenant_id,
        llm_provider="ollama",
        query="Explain HTTP/2 multiplexing.",
    )

    assert result is None
    assert key not in client.values


@pytest.mark.anyio
async def test_delete_removes_cached_result() -> None:
    client = RecordingTextCacheClient()
    cache = RedisResearchResultCache(
        client,
        ttl_seconds=900,
    )
    tenant_id = uuid4()

    await cache.set(
        tenant_id=tenant_id,
        query="Explain idempotency.",
        result=create_cached_result(),
    )

    first_delete = await cache.delete(
        tenant_id=tenant_id,
        llm_provider="ollama",
        query="Explain idempotency.",
    )
    second_delete = await cache.delete(
        tenant_id=tenant_id,
        llm_provider="ollama",
        query="Explain idempotency.",
    )

    assert first_delete is True
    assert second_delete is False


def test_cache_rejects_non_positive_ttl() -> None:
    with pytest.raises(
        ValueError,
        match="ttl_seconds must be at least 1",
    ):
        RedisResearchResultCache(
            RecordingTextCacheClient(),
            ttl_seconds=0,
        )
