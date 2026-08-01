from uuid import UUID

from pydantic import ValidationError

from app.core.config import settings
from app.schemas.progress import ResearchProgressRecord
from app.services.cache.base import TextCacheClient
from app.services.cache.keys import (
    create_research_progress_redis_key,
)


class RedisResearchProgressStore:
    """Store the latest tenant-scoped progress snapshot for a research run."""

    def __init__(
        self,
        client: TextCacheClient,
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        selected_ttl = (
            ttl_seconds if ttl_seconds is not None else settings.redis_research_progress_ttl_seconds
        )

        if selected_ttl < 1:
            raise ValueError("Research progress ttl_seconds must be at least 1.")

        self._client = client
        self._ttl_seconds = selected_ttl

    async def get(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> ResearchProgressRecord | None:
        """Return one validated progress snapshot or a cache miss."""

        key = create_research_progress_redis_key(
            tenant_id=tenant_id,
            research_run_id=research_run_id,
        )
        raw_payload = await self._client.get_text(
            key=key,
        )

        if raw_payload is None:
            return None

        try:
            record = ResearchProgressRecord.model_validate_json(
                raw_payload,
            )
        except ValidationError:
            await self._client.delete(
                key=key,
            )
            return None

        if record.research_run_id != research_run_id:
            await self._client.delete(
                key=key,
            )
            return None

        return record

    async def set(
        self,
        *,
        tenant_id: UUID,
        record: ResearchProgressRecord,
    ) -> None:
        """Store the latest progress snapshot with expiration."""

        key = create_research_progress_redis_key(
            tenant_id=tenant_id,
            research_run_id=record.research_run_id,
        )

        await self._client.set_text(
            key=key,
            value=record.model_dump_json(),
            ttl_seconds=self._ttl_seconds,
        )

    async def delete(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> bool:
        """Delete one tenant-scoped progress snapshot."""

        key = create_research_progress_redis_key(
            tenant_id=tenant_id,
            research_run_id=research_run_id,
        )

        return await self._client.delete(
            key=key,
        )
