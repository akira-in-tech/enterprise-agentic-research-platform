import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from anthropic import AsyncAnthropic
from anthropic.types import Message, TextBlock
from anthropic.types.parsed_message import ParsedMessage
from pydantic import BaseModel

from app.core.circuit_breaker import CircuitBreaker
from app.core.config import settings

logger = logging.getLogger(__name__)
StructuredModel = TypeVar("StructuredModel", bound=BaseModel)
ResponseT = TypeVar("ResponseT")


class AnthropicClient:
    """Provide a small application-facing wrapper around the Anthropic SDK."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        configured_api_key = (
            settings.anthropic_api_key.get_secret_value() if api_key is None else api_key
        ).strip()
        configured_model = (settings.anthropic_model if model is None else model).strip()

        if not configured_api_key:
            raise ValueError("ANTHROPIC_API_KEY is not configured.")

        if not configured_model:
            raise ValueError("ANTHROPIC_MODEL is not configured.")

        self._model = configured_model
        self._client = AsyncAnthropic(
            api_key=configured_api_key,
            timeout=120.0,
            max_retries=2,
        )
        self._circuit_breaker = circuit_breaker

    async def generate_text(
        self,
        prompt: str,
        *,
        max_tokens: int = 64,
    ) -> str:
        """Generate a short text response from Claude."""

        normalized_prompt = prompt.strip()

        if not normalized_prompt:
            raise ValueError("Prompt must not be empty.")

        logger.info(
            "Sending Claude request | model=%s | max_tokens=%s",
            self._model,
            max_tokens,
        )

        async def call_claude() -> Message:
            return await self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": normalized_prompt,
                    }
                ],
            )

        message = await self._call(call_claude)

        text_parts = [block.text for block in message.content if isinstance(block, TextBlock)]

        response_text = "\n".join(text_parts).strip()

        if not response_text:
            raise RuntimeError("Claude returned no text content.")

        logger.info(
            "Claude request completed | input_tokens=%s | output_tokens=%s",
            message.usage.input_tokens,
            message.usage.output_tokens,
        )

        return response_text

    async def generate_structured(
        self,
        prompt: str,
        output_model: type[StructuredModel],
        *,
        max_tokens: int = 256,
    ) -> StructuredModel:
        """Generate and validate a structured Claude response."""

        normalized_prompt = prompt.strip()

        if not normalized_prompt:
            raise ValueError("Prompt must not be empty.")

        logger.info(
            "Sending structured Claude request | model=%s | schema=%s",
            self._model,
            output_model.__name__,
        )

        async def call_claude() -> ParsedMessage[StructuredModel]:
            return await self._client.messages.parse(
                model=self._model,
                max_tokens=max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": normalized_prompt,
                    }
                ],
                output_format=output_model,
            )

        message = await self._call(call_claude)

        parsed_output = message.parsed_output

        if parsed_output is None:
            raise RuntimeError("Claude returned no structured output.")

        logger.info(
            "Structured Claude request completed | schema=%s",
            output_model.__name__,
        )

        return parsed_output

    async def _call(
        self,
        func: Callable[[], Awaitable[ResponseT]],
    ) -> ResponseT:
        """Run one Anthropic SDK call, through the circuit breaker if configured."""

        if self._circuit_breaker is None:
            return await func()

        return await self._circuit_breaker.call(func)

    async def close(self) -> None:
        """Close the underlying Anthropic client."""

        await self._client.close()
