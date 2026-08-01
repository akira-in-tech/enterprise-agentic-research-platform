from typing import cast
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.idempotency import ResearchIdempotencyRecord
from app.schemas.research import (
    CreateResearchRunResponse,
    PersistedLLMProvider,
)
from app.services.cache import (
    create_research_request_fingerprint,
)


def create_test_response() -> CreateResearchRunResponse:
    return CreateResearchRunResponse(
        research_run_id=uuid4(),
        llm_provider="ollama",
        status="completed",
        cache_hit=False,
        workflow_status="direct_answer_completed",
        route="direct",
        route_reason="The question uses stable knowledge.",
        answer="A mutex protects a critical section.",
    )


def test_request_fingerprint_is_deterministic() -> None:
    user_id = uuid4()

    first_fingerprint = create_research_request_fingerprint(
        query="What is a mutex?",
        llm_provider="ollama",
        requested_by_user_id=user_id,
    )
    second_fingerprint = create_research_request_fingerprint(
        query="What is a mutex?",
        llm_provider="ollama",
        requested_by_user_id=user_id,
    )

    assert first_fingerprint == second_fingerprint
    assert len(first_fingerprint) == 64


def test_request_fingerprint_normalizes_outer_query_whitespace() -> None:
    normalized_fingerprint = create_research_request_fingerprint(
        query="Explain HTTP keep-alive.",
        llm_provider="ollama",
        requested_by_user_id=None,
    )
    padded_fingerprint = create_research_request_fingerprint(
        query="  Explain HTTP keep-alive.  ",
        llm_provider="ollama",
        requested_by_user_id=None,
    )

    assert normalized_fingerprint == padded_fingerprint


def test_request_fingerprint_isolates_providers() -> None:
    qwen_fingerprint = create_research_request_fingerprint(
        query="Explain DNS.",
        llm_provider="ollama",
        requested_by_user_id=None,
    )
    claude_fingerprint = create_research_request_fingerprint(
        query="Explain DNS.",
        llm_provider="anthropic",
        requested_by_user_id=None,
    )

    assert qwen_fingerprint != claude_fingerprint


def test_request_fingerprint_isolates_users() -> None:
    first_fingerprint = create_research_request_fingerprint(
        query="Explain Linux epoll.",
        llm_provider="ollama",
        requested_by_user_id=uuid4(),
    )
    second_fingerprint = create_research_request_fingerprint(
        query="Explain Linux epoll.",
        llm_provider="ollama",
        requested_by_user_id=uuid4(),
    )

    assert first_fingerprint != second_fingerprint


def test_request_fingerprint_does_not_expose_request_data() -> None:
    user_id = uuid4()
    query = "Review confidential acquisition strategy."

    fingerprint = create_research_request_fingerprint(
        query=query,
        llm_provider="anthropic",
        requested_by_user_id=user_id,
    )

    assert query not in fingerprint
    assert "confidential" not in fingerprint
    assert str(user_id) not in fingerprint


@pytest.mark.parametrize(
    "query",
    [
        "",
        "   ",
        "\n\t",
    ],
)
def test_request_fingerprint_rejects_blank_query(
    query: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="query must not be empty",
    ):
        create_research_request_fingerprint(
            query=query,
            llm_provider="ollama",
            requested_by_user_id=None,
        )


def test_request_fingerprint_rejects_unknown_provider() -> None:
    invalid_provider = cast(
        PersistedLLMProvider,
        "openai",
    )

    with pytest.raises(
        ValueError,
        match="Unsupported fingerprint LLM provider",
    ):
        create_research_request_fingerprint(
            query="Explain DNS.",
            llm_provider=invalid_provider,
            requested_by_user_id=None,
        )


def test_idempotency_record_serializes_and_restores() -> None:
    record = ResearchIdempotencyRecord(
        request_fingerprint=(
            create_research_request_fingerprint(
                query="What is a mutex?",
                llm_provider="ollama",
                requested_by_user_id=None,
            )
        ),
        response=create_test_response(),
    )

    restored_record = ResearchIdempotencyRecord.model_validate_json(
        record.model_dump_json(),
    )

    assert restored_record == record


def test_idempotency_record_rejects_invalid_fingerprint() -> None:
    with pytest.raises(ValidationError):
        ResearchIdempotencyRecord(
            request_fingerprint="not-a-sha256-digest",
            response=create_test_response(),
        )


def test_idempotency_record_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ResearchIdempotencyRecord.model_validate(
            {
                "request_fingerprint": "a" * 64,
                "response": create_test_response(),
                "unexpected": True,
            }
        )
