from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from anthropic.types import TextBlock

from app.services.llm.anthropic import AnthropicClient


@pytest.mark.anyio
async def test_generate_text_returns_anthropic_text() -> None:
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

    client._client.messages.create = AsyncMock(return_value=mock_message)

    result = await client.generate_text(
        "Confirm the API works.",
        max_tokens=32,
    )

    assert result == "The API works correctly."
    client._client.messages.create.assert_awaited_once()


@pytest.mark.anyio
async def test_generate_text_rejects_empty_prompt() -> None:
    client = AnthropicClient()

    with pytest.raises(ValueError, match="Prompt must not be empty"):
        await client.generate_text("   ")


@pytest.mark.anyio
async def test_generate_text_raises_when_no_text_is_returned() -> None:
    client = AnthropicClient()

    mock_message = SimpleNamespace(
        content=[],
        usage=SimpleNamespace(
            input_tokens=8,
            output_tokens=0,
        ),
    )

    client._client.messages.create = AsyncMock(return_value=mock_message)

    with pytest.raises(RuntimeError, match="Claude returned no text content"):
        await client.generate_text("Return a response.")