from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from anthropic.types import TextBlock

from app.services.llm.anthropic import AnthropicClient


@pytest.mark.anyio
async def test_generate_text_returns_anthropic_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = AnthropicClient()

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
    client = AnthropicClient()

    with pytest.raises(ValueError, match="Prompt must not be empty"):
        await client.generate_text("   ")


@pytest.mark.anyio
async def test_generate_text_raises_when_no_text_is_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = AnthropicClient()

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
async def test_close_releases_anthropic_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = AnthropicClient()
    close_client = AsyncMock()

    monkeypatch.setattr(
        client._client,
        "close",
        close_client,
    )

    await client.close()

    close_client.assert_awaited_once_with()
