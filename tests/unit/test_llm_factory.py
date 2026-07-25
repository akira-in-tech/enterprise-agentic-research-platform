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


def test_factory_uses_provider_from_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_client = object()

    monkeypatch.setattr(
        settings,
        "llm_provider",
        "ollama",
    )
    monkeypatch.setattr(
        factory,
        "OllamaClient",
        lambda: expected_client,
    )

    result = factory.create_llm_client()

    assert result is expected_client


def test_factory_rejects_unsupported_provider() -> None:
    with pytest.raises(
        ValueError,
        match="Unsupported LLM provider",
    ):
        factory.create_llm_client("unknown-provider")
