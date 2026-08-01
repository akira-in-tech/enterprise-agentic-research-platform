import json
from hashlib import sha256
from uuid import UUID

from app.schemas.research import PersistedLLMProvider


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
