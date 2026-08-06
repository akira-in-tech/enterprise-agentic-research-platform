from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from anthropic.types import TextBlock

from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from app.schemas.intent import IntentDecision
from app.services.llm.anthropic import AnthropicClient


@pytest.mark.anyio
async def test_generate_text_returns_anthropic_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = AnthropicClient(
        api_key="test-api-key",
        model="test-model",
    )

    mock_message = SimpleNamespace(
        content=[
            TextBlock(
                type="text",
                text="The API works correctly.",
                citations=None,
            )
        ],
        usage=SimpleNamespace(
            input_tokens=8,
            output_tokens=5,
        ),
    )

    create_message = AsyncMock(return_value=mock_message)
    monkeypatch.setattr(
        client._client.messages,
        "create",
        create_message,
    )

    result = await client.generate_text(
        "Confirm the API works.",
        max_tokens=32,
    )

    assert result == "The API works correctly."
    create_message.assert_awaited_once()


@pytest.mark.anyio
async def test_generate_text_rejects_empty_prompt() -> None:
    client = AnthropicClient(
        api_key="test-api-key",
        model="test-model",
    )

    with pytest.raises(ValueError, match="Prompt must not be empty"):
        await client.generate_text("   ")


@pytest.mark.anyio
async def test_generate_text_raises_when_no_text_is_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = AnthropicClient(
        api_key="test-api-key",
        model="test-model",
    )

    mock_message = SimpleNamespace(
        content=[],
        usage=SimpleNamespace(
            input_tokens=8,
            output_tokens=0,
        ),
    )

    monkeypatch.setattr(
        client._client.messages,
        "create",
        AsyncMock(return_value=mock_message),
    )

    with pytest.raises(RuntimeError, match="Claude returned no text content"):
        await client.generate_text("Return a response.")


@pytest.mark.anyio
async def test_generate_text_opens_the_circuit_after_repeated_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout_seconds=60)
    client = AnthropicClient(
        api_key="test-api-key",
        model="test-model",
        circuit_breaker=breaker,
    )
    create_message = AsyncMock(side_effect=RuntimeError("Anthropic is unavailable."))
    monkeypatch.setattr(client._client.messages, "create", create_message)

    for _ in range(2):
        with pytest.raises(RuntimeError, match="Anthropic is unavailable"):
            await client.generate_text("Confirm the API works.")

    with pytest.raises(CircuitBreakerOpenError):
        await client.generate_text("Confirm the API works.")

    # The third call was rejected locally by the breaker, not sent to Anthropic.
    assert create_message.await_count == 2


@pytest.mark.anyio
async def test_generate_structured_opens_the_circuit_after_repeated_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout_seconds=60)
    client = AnthropicClient(
        api_key="test-api-key",
        model="test-model",
        circuit_breaker=breaker,
    )
    parse_message = AsyncMock(side_effect=RuntimeError("Anthropic is unavailable."))
    monkeypatch.setattr(client._client.messages, "parse", parse_message)

    with pytest.raises(RuntimeError, match="Anthropic is unavailable"):
        await client.generate_structured("Classify this.", IntentDecision)

    with pytest.raises(CircuitBreakerOpenError):
        await client.generate_structured("Classify this.", IntentDecision)

    assert parse_message.await_count == 1


@pytest.mark.anyio
async def test_generate_structured_succeeds_without_a_configured_breaker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = AnthropicClient(
        api_key="test-api-key",
        model="test-model",
    )
    decision = IntentDecision(route="direct", reason="Stable knowledge is sufficient.")
    monkeypatch.setattr(
        client._client.messages,
        "parse",
        AsyncMock(return_value=SimpleNamespace(parsed_output=decision)),
    )

    result = await client.generate_structured("Classify this.", IntentDecision)

    assert result == decision


@pytest.mark.anyio
async def test_close_releases_anthropic_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = AnthropicClient(
        api_key="test-api-key",
        model="test-model",
    )
    close_client = AsyncMock()

    monkeypatch.setattr(
        client._client,
        "close",
        close_client,
    )

    await client.close()

    close_client.assert_awaited_once_with()
