import pytest

from app.core.config import settings
from app.services.llm import factory


def test_factory_creates_anthropic_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_client = object()

    monkeypatch.setattr(
        factory,
        "AnthropicClient",
        lambda: expected_client,
    )

    result = factory.create_llm_client("anthropic")

    assert result is expected_client


def test_factory_creates_ollama_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_client = object()

    monkeypatch.setattr(
        factory,
        "OllamaClient",
        lambda: expected_client,
    )

    result = factory.create_llm_client("ollama")

    assert result is expected_client


@pytest.mark.parametrize(
    ("provider", "constructor_name"),
    [
        (
            "claude",
            "AnthropicClient",
        ),
        (
            "qwen",
            "OllamaClient",
        ),
    ],
)
def test_factory_accepts_user_facing_aliases(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    constructor_name: str,
) -> None:
    expected_client = object()

    monkeypatch.setattr(
        factory,
        constructor_name,
        lambda: expected_client,
    )

    result = factory.create_llm_client(provider)

    assert result is expected_client


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        (
            " ANTHROPIC ",
            "anthropic",
        ),
        (
            " Claude ",
            "anthropic",
        ),
        (
            " OLLAMA ",
            "ollama",
        ),
        (
            " Qwen ",
            "ollama",
        ),
    ],
)
def test_normalize_llm_provider(
    provider: str,
    expected: factory.CanonicalLLMProvider,
) -> None:
    assert factory.normalize_llm_provider(provider) == expected


def test_factory_uses_provider_from_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_client = object()

    monkeypatch.setattr(
        settings,
        "llm_provider",
        "qwen",
    )
    monkeypatch.setattr(
        factory,
        "OllamaClient",
        lambda: expected_client,
    )

    result = factory.create_llm_client()

    assert result is expected_client


@pytest.mark.parametrize(
    "provider",
    [
        "",
        "unknown-provider",
    ],
)
def test_factory_rejects_unsupported_provider(
    provider: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="Unsupported LLM provider",
    ):
        factory.create_llm_client(provider)
