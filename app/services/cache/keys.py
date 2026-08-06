from collections.abc import Sequence
from hashlib import sha256
from uuid import UUID

from app.schemas.research import PersistedLLMProvider

RESEARCH_RESULT_CACHE_VERSION = "v2"
RESEARCH_IDEMPOTENCY_KEY_VERSION = "v1"
MAX_RESEARCH_IDEMPOTENCY_KEY_LENGTH = 200
RESEARCH_IDEMPOTENCY_LOCK_VERSION = "v1"
RESEARCH_RATE_LIMIT_VERSION = "v1"
RESEARCH_PROGRESS_VERSION = "v1"


def create_research_result_cache_key(
    *,
    tenant_id: UUID,
    llm_provider: PersistedLLMProvider,
    query: str,
    document_ids: Sequence[str] | None = None,
) -> str:
    """Create a versioned, tenant-scoped research result cache key.

    document_ids scopes the underlying private-knowledge search, so it must
    be part of the digest -- otherwise two requests with the same query text
    but different document scoping would collide on the same cache entry.
    None means "search every tenant document" and is distinct from an empty
    sequence, which means "search none".
    """

    normalized_query = query.strip()

    if not normalized_query:
        raise ValueError("query must not be empty.")

    if llm_provider not in {
        "anthropic",
        "ollama",
    }:
        raise ValueError(f"Unsupported cache LLM provider: {llm_provider}.")

    if document_ids is None:
        scope_marker = "all"
    else:
        sorted_document_ids = sorted(document_id.strip() for document_id in document_ids)
        scope_marker = "documents:" + ",".join(sorted_document_ids)

    query_digest = sha256(
        f"{normalized_query}\n{scope_marker}".encode(),
    ).hexdigest()

    return (
        "enterprise-research"
        f":{RESEARCH_RESULT_CACHE_VERSION}"
        f":tenant:{tenant_id}"
        f":research-result:{llm_provider}"
        f":{query_digest}"
    )


def _create_idempotency_client_key_digest(
    client_key: str,
) -> str:
    """Validate and hash one client-supplied idempotency key."""

    normalized_client_key = client_key.strip()

    if not normalized_client_key:
        raise ValueError("client_key must not be empty.")

    if len(normalized_client_key) > MAX_RESEARCH_IDEMPOTENCY_KEY_LENGTH:
        raise ValueError(
            f"client_key must not exceed {MAX_RESEARCH_IDEMPOTENCY_KEY_LENGTH} characters."
        )

    return sha256(
        normalized_client_key.encode(),
    ).hexdigest()


def create_research_idempotency_redis_key(
    *,
    tenant_id: UUID,
    client_key: str,
) -> str:
    """Create a versioned, tenant-scoped Redis idempotency key."""

    client_key_digest = _create_idempotency_client_key_digest(
        client_key,
    )

    return (
        "enterprise-research"
        f":{RESEARCH_IDEMPOTENCY_KEY_VERSION}"
        f":tenant:{tenant_id}"
        f":research-idempotency:{client_key_digest}"
    )


def create_research_idempotency_lock_redis_key(
    *,
    tenant_id: UUID,
    client_key: str,
) -> str:
    """Create a tenant-scoped Redis coordination-lock key."""

    client_key_digest = _create_idempotency_client_key_digest(
        client_key,
    )

    return (
        "enterprise-research"
        f":{RESEARCH_IDEMPOTENCY_LOCK_VERSION}"
        f":tenant:{tenant_id}"
        f":research-idempotency-lock:{client_key_digest}"
    )


def create_research_rate_limit_redis_key(
    *,
    tenant_id: UUID,
) -> str:
    """Create a versioned, tenant-scoped research rate-limit key."""

    return (
        f"enterprise-research:{RESEARCH_RATE_LIMIT_VERSION}:tenant:{tenant_id}:research-rate-limit"
    )


def create_research_progress_redis_key(
    *,
    tenant_id: UUID,
    research_run_id: UUID,
) -> str:
    """Create a versioned, tenant-scoped research progress key."""

    return (
        f"enterprise-research:{RESEARCH_PROGRESS_VERSION}"
        f":tenant:{tenant_id}:research-progress:{research_run_id}"
    )
