import json
from hashlib import sha256
from uuid import UUID

from pydantic import ValidationError

from app.core.config import settings
from app.schemas.idempotency import ResearchIdempotencyRecord
from app.schemas.research import PersistedLLMProvider
from app.services.cache.base import TextCacheClient
from app.services.cache.keys import (
    create_research_idempotency_redis_key,
)


def create_research_request_fingerprint(
    *,
    query: str,
    llm_provider: PersistedLLMProvider,
    requested_by_user_id: UUID | None,
) -> str:
    """Hash the canonical fields that define one research request."""

    normalized_query = query.strip()

    if not normalized_query:
        raise ValueError("query must not be empty.")

    if llm_provider not in {
        "anthropic",
        "ollama",
    }:
        raise ValueError(f"Unsupported fingerprint LLM provider: {llm_provider}.")

    canonical_request = json.dumps(
        {
            "llm_provider": llm_provider,
            "query": normalized_query,
            "requested_by_user_id": (
                str(requested_by_user_id) if requested_by_user_id is not None else None
            ),
        },
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=False,
    )

    return sha256(
        canonical_request.encode(),
    ).hexdigest()


class RedisResearchIdempotencyStore:
    """Store completed tenant-scoped idempotency records."""

    def __init__(
        self,
        client: TextCacheClient,
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        selected_ttl = (
            ttl_seconds
            if ttl_seconds is not None
            else settings.redis_research_idempotency_ttl_seconds
        )

        if selected_ttl < 1:
            raise ValueError("Research idempotency ttl_seconds must be at least 1.")

        self._client = client
        self._ttl_seconds = selected_ttl

    async def get(
        self,
        *,
        tenant_id: UUID,
        client_key: str,
    ) -> ResearchIdempotencyRecord | None:
        """Return one validated idempotency record or a cache miss."""

        redis_key = create_research_idempotency_redis_key(
            tenant_id=tenant_id,
            client_key=client_key,
        )
        raw_payload = await self._client.get_text(
            key=redis_key,
        )

        if raw_payload is None:
            return None

        try:
            return ResearchIdempotencyRecord.model_validate_json(
                raw_payload,
            )
        except ValidationError:
            await self._client.delete(
                key=redis_key,
            )
            return None

    async def set(
        self,
        *,
        tenant_id: UUID,
        client_key: str,
        record: ResearchIdempotencyRecord,
    ) -> None:
        """Serialize and store one completed idempotency record."""

        redis_key = create_research_idempotency_redis_key(
            tenant_id=tenant_id,
            client_key=client_key,
        )

        await self._client.set_text(
            key=redis_key,
            value=record.model_dump_json(),
            ttl_seconds=self._ttl_seconds,
        )

    async def delete(
        self,
        *,
        tenant_id: UUID,
        client_key: str,
    ) -> bool:
        """Delete one tenant-scoped idempotency record."""

        redis_key = create_research_idempotency_redis_key(
            tenant_id=tenant_id,
            client_key=client_key,
        )

        return await self._client.delete(
            key=redis_key,
        )
