from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.schemas.progress import ResearchProgressRecord
from app.services.cache import (
    RedisResearchProgressStore,
    create_research_progress_redis_key,
)


class RecordingTextCacheClient:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int]] = []
        self.deleted: list[str] = []

    async def get_text(self, *, key: str) -> str | None:
        return self.values.get(key)

    async def set_text(
        self,
        *,
        key: str,
        value: str,
        ttl_seconds: int,
    ) -> None:
        self.values[key] = value
        self.set_calls.append((key, value, ttl_seconds))

    async def delete(self, *, key: str) -> bool:
        self.deleted.append(key)
        return self.values.pop(key, None) is not None


def test_progress_key_is_versioned_and_tenant_scoped() -> None:
    tenant_id = uuid4()
    research_run_id = uuid4()

    key = create_research_progress_redis_key(
        tenant_id=tenant_id,
        research_run_id=research_run_id,
    )

    assert key == (f"enterprise-research:v1:tenant:{tenant_id}:research-progress:{research_run_id}")


@pytest.mark.anyio
async def test_progress_store_round_trip_uses_ttl() -> None:
    client = RecordingTextCacheClient()
    store = RedisResearchProgressStore(client, ttl_seconds=120)
    tenant_id = uuid4()
    record = ResearchProgressRecord(
        research_run_id=uuid4(),
        status="running",
        message="Research workflow is running.",
        updated_at=datetime.now(UTC),
    )

    await store.set(tenant_id=tenant_id, record=record)
    restored = await store.get(
        tenant_id=tenant_id,
        research_run_id=record.research_run_id,
    )

    assert restored == record
    assert client.set_calls[0][2] == 120


@pytest.mark.anyio
async def test_progress_store_isolates_tenants() -> None:
    client = RecordingTextCacheClient()
    store = RedisResearchProgressStore(client, ttl_seconds=120)
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    record = ResearchProgressRecord(
        research_run_id=uuid4(),
        status="queued",
        message="Research request queued.",
        updated_at=datetime.now(UTC),
    )

    await store.set(tenant_id=tenant_id, record=record)

    assert (
        await store.get(
            tenant_id=other_tenant_id,
            research_run_id=record.research_run_id,
        )
        is None
    )


@pytest.mark.anyio
async def test_progress_store_deletes_invalid_payload() -> None:
    client = RecordingTextCacheClient()
    store = RedisResearchProgressStore(client, ttl_seconds=120)
    tenant_id = uuid4()
    research_run_id = uuid4()
    key = create_research_progress_redis_key(
        tenant_id=tenant_id,
        research_run_id=research_run_id,
    )
    client.values[key] = "not-json"

    result = await store.get(
        tenant_id=tenant_id,
        research_run_id=research_run_id,
    )

    assert result is None
    assert client.deleted == [key]


def test_progress_store_rejects_non_positive_ttl() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        RedisResearchProgressStore(RecordingTextCacheClient(), ttl_seconds=0)
