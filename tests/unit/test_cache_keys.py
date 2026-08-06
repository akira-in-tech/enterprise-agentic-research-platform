from typing import cast
from uuid import uuid4

import pytest

from app.schemas.research import PersistedLLMProvider
from app.services.cache.keys import (
    RESEARCH_RESULT_CACHE_VERSION,
    create_research_result_cache_key,
)


def test_research_result_cache_key_is_deterministic() -> None:
    tenant_id = uuid4()

    first_key = create_research_result_cache_key(
        tenant_id=tenant_id,
        llm_provider="ollama",
        query="Explain DNS recursive resolution.",
    )
    second_key = create_research_result_cache_key(
        tenant_id=tenant_id,
        llm_provider="ollama",
        query="Explain DNS recursive resolution.",
    )

    assert first_key == second_key
    assert first_key.startswith(
        "enterprise-research"
        f":{RESEARCH_RESULT_CACHE_VERSION}"
        f":tenant:{tenant_id}"
        ":research-result:ollama:"
    )


def test_cache_key_normalizes_outer_query_whitespace() -> None:
    tenant_id = uuid4()

    normalized_key = create_research_result_cache_key(
        tenant_id=tenant_id,
        llm_provider="anthropic",
        query="Compare HTTP/2 and HTTP/3.",
    )
    padded_key = create_research_result_cache_key(
        tenant_id=tenant_id,
        llm_provider="anthropic",
        query="  Compare HTTP/2 and HTTP/3.  ",
    )

    assert normalized_key == padded_key


def test_cache_key_preserves_meaningful_internal_whitespace() -> None:
    tenant_id = uuid4()

    first_key = create_research_result_cache_key(
        tenant_id=tenant_id,
        llm_provider="ollama",
        query="Explain HTTP keep-alive.",
    )
    second_key = create_research_result_cache_key(
        tenant_id=tenant_id,
        llm_provider="ollama",
        query="Explain  HTTP keep-alive.",
    )

    assert first_key != second_key


def test_cache_key_isolates_document_scope() -> None:
    tenant_id = uuid4()

    all_documents_key = create_research_result_cache_key(
        tenant_id=tenant_id,
        llm_provider="ollama",
        query="Summarize the onboarding policy.",
    )
    no_documents_key = create_research_result_cache_key(
        tenant_id=tenant_id,
        llm_provider="ollama",
        query="Summarize the onboarding policy.",
        document_ids=[],
    )
    scoped_key = create_research_result_cache_key(
        tenant_id=tenant_id,
        llm_provider="ollama",
        query="Summarize the onboarding policy.",
        document_ids=["DOC-0000000000000001"],
    )
    other_scoped_key = create_research_result_cache_key(
        tenant_id=tenant_id,
        llm_provider="ollama",
        query="Summarize the onboarding policy.",
        document_ids=["DOC-0000000000000002"],
    )

    assert len({all_documents_key, no_documents_key, scoped_key, other_scoped_key}) == 4


def test_cache_key_ignores_document_id_order() -> None:
    tenant_id = uuid4()

    first_key = create_research_result_cache_key(
        tenant_id=tenant_id,
        llm_provider="ollama",
        query="Summarize the onboarding policy.",
        document_ids=["DOC-A", "DOC-B"],
    )
    second_key = create_research_result_cache_key(
        tenant_id=tenant_id,
        llm_provider="ollama",
        query="Summarize the onboarding policy.",
        document_ids=["DOC-B", "DOC-A"],
    )

    assert first_key == second_key


def test_cache_key_isolates_tenants() -> None:
    first_key = create_research_result_cache_key(
        tenant_id=uuid4(),
        llm_provider="ollama",
        query="Explain Linux epoll.",
    )
    second_key = create_research_result_cache_key(
        tenant_id=uuid4(),
        llm_provider="ollama",
        query="Explain Linux epoll.",
    )

    assert first_key != second_key


def test_cache_key_isolates_llm_providers() -> None:
    tenant_id = uuid4()

    claude_key = create_research_result_cache_key(
        tenant_id=tenant_id,
        llm_provider="anthropic",
        query="Explain idempotency in REST APIs.",
    )
    qwen_key = create_research_result_cache_key(
        tenant_id=tenant_id,
        llm_provider="ollama",
        query="Explain idempotency in REST APIs.",
    )

    assert claude_key != qwen_key


def test_cache_key_does_not_expose_raw_query() -> None:
    query = "Compare our confidential platform architecture with public cloud guidance."

    cache_key = create_research_result_cache_key(
        tenant_id=uuid4(),
        llm_provider="anthropic",
        query=query,
    )

    assert query not in cache_key
    assert "confidential" not in cache_key


@pytest.mark.parametrize(
    "query",
    [
        "",
        "   ",
        "\n\t",
    ],
)
def test_cache_key_rejects_blank_query(
    query: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="query must not be empty",
    ):
        create_research_result_cache_key(
            tenant_id=uuid4(),
            llm_provider="ollama",
            query=query,
        )


def test_cache_key_rejects_unknown_provider() -> None:
    invalid_provider = cast(
        PersistedLLMProvider,
        "openai",
    )

    with pytest.raises(
        ValueError,
        match="Unsupported cache LLM provider",
    ):
        create_research_result_cache_key(
            tenant_id=uuid4(),
            llm_provider=invalid_provider,
            query="Explain DNS.",
        )
