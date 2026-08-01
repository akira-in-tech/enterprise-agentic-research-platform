from hashlib import sha256
from uuid import UUID

from app.schemas.research import PersistedLLMProvider

RESEARCH_RESULT_CACHE_VERSION = "v1"


def create_research_result_cache_key(
    *,
    tenant_id: UUID,
    llm_provider: PersistedLLMProvider,
    query: str,
) -> str:
    """Create a versioned, tenant-scoped research result cache key."""

    normalized_query = query.strip()

    if not normalized_query:
        raise ValueError("query must not be empty.")

    if llm_provider not in {
        "anthropic",
        "ollama",
    }:
        raise ValueError(f"Unsupported cache LLM provider: {llm_provider}.")

    query_digest = sha256(
        normalized_query.encode(),
    ).hexdigest()

    return (
        "enterprise-research"
        f":{RESEARCH_RESULT_CACHE_VERSION}"
        f":tenant:{tenant_id}"
        f":research-result:{llm_provider}"
        f":{query_digest}"
    )
