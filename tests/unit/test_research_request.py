import pytest
from pydantic import ValidationError

from app.schemas.research import CreateResearchRunRequest


@pytest.mark.parametrize(
    "provider",
    [
        "claude",
        "qwen",
    ],
)
def test_research_request_accepts_user_facing_provider(
    provider: str,
) -> None:
    request = CreateResearchRunRequest(
        query="Explain Linux epoll.",
        llm_provider=provider,  # type: ignore[arg-type]
    )

    assert request.query == "Explain Linux epoll."
    assert request.llm_provider == provider


def test_research_request_strips_query_whitespace() -> None:
    request = CreateResearchRunRequest(
        query="  Compare HTTP/2 and HTTP/3.  ",
        llm_provider="qwen",
    )

    assert request.query == "Compare HTTP/2 and HTTP/3."


def test_research_request_rejects_blank_query() -> None:
    with pytest.raises(ValidationError):
        CreateResearchRunRequest(
            query="   ",
            llm_provider="qwen",
        )


@pytest.mark.parametrize(
    "provider",
    [
        "anthropic",
        "ollama",
        "openai",
    ],
)
def test_research_request_rejects_internal_provider_names(
    provider: str,
) -> None:
    with pytest.raises(ValidationError):
        CreateResearchRunRequest.model_validate(
            {
                "query": "Explain database isolation levels.",
                "llm_provider": provider,
            }
        )
