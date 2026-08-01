from typing import Protocol
from uuid import UUID

from pydantic import ValidationError

from app.core.config import settings
from app.schemas.cache import CachedResearchResult
from app.schemas.research import PersistedLLMProvider
from app.services.cache.keys import (
    create_research_result_cache_key,
)


class TextCacheClient(Protocol):
    """Text operations required by the research-result cache."""

    async def get_text(
        self,
        *,
        key: str,
    ) -> str | None:
        """Return one cached text value."""

    async def set_text(
        self,
        *,
        key: str,
        value: str,
        ttl_seconds: int,
    ) -> None:
        """Store one text value with expiration."""

    async def delete(
        self,
        *,
        key: str,
    ) -> bool:
        """Delete one cached value."""


class RedisResearchResultCache:
    """Store tenant-scoped research result payloads in Redis."""

    def __init__(
        self,
        client: TextCacheClient,
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        selected_ttl = (
            ttl_seconds if ttl_seconds is not None else settings.redis_research_result_ttl_seconds
        )

        if selected_ttl < 1:
            raise ValueError("Research result cache ttl_seconds must be at least 1.")

        self._client = client
        self._ttl_seconds = selected_ttl

    async def get(
        self,
        *,
        tenant_id: UUID,
        llm_provider: PersistedLLMProvider,
        query: str,
    ) -> CachedResearchResult | None:
        """Return one validated cached result or a cache miss."""

        key = create_research_result_cache_key(
            tenant_id=tenant_id,
            llm_provider=llm_provider,
            query=query,
        )
        raw_payload = await self._client.get_text(
            key=key,
        )

        if raw_payload is None:
            return None

        try:
            result = CachedResearchResult.model_validate_json(
                raw_payload,
            )
        except ValidationError:
            await self._client.delete(
                key=key,
            )
            return None

        if result.llm_provider != llm_provider:
            await self._client.delete(
                key=key,
            )
            return None

        return result

    async def set(
        self,
        *,
        tenant_id: UUID,
        query: str,
        result: CachedResearchResult,
    ) -> None:
        """Serialize and cache one research result."""

        key = create_research_result_cache_key(
            tenant_id=tenant_id,
            llm_provider=result.llm_provider,
            query=query,
        )

        await self._client.set_text(
            key=key,
            value=result.model_dump_json(),
            ttl_seconds=self._ttl_seconds,
        )

    async def delete(
        self,
        *,
        tenant_id: UUID,
        llm_provider: PersistedLLMProvider,
        query: str,
    ) -> bool:
        """Delete one tenant-scoped cached result."""

        key = create_research_result_cache_key(
            tenant_id=tenant_id,
            llm_provider=llm_provider,
            query=query,
        )

        return await self._client.delete(
            key=key,
        )
