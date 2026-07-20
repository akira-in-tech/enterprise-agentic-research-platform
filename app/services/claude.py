import logging

from anthropic import AsyncAnthropic
from anthropic.types import TextBlock

from app.core.config import settings

from typing import TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)
StructuredModel = TypeVar("StructuredModel", bound=BaseModel)

class ClaudeClient:
    """Provide a small application-facing wrapper around the Anthropic SDK."""

    def __init__(self) -> None:
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is not configured.")

        if not settings.anthropic_model:
            raise ValueError("ANTHROPIC_MODEL is not configured.")

        self._model = settings.anthropic_model
        self._client = AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            timeout=30.0,
            max_retries=2,
        )

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

        message = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": normalized_prompt,
                }
            ],
        )

        text_parts = [
            block.text
            for block in message.content
            if isinstance(block, TextBlock)
        ]

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

        message = await self._client.messages.parse(
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

        parsed_output = message.parsed_output

        if parsed_output is None:
            raise RuntimeError("Claude returned no structured output.")

        logger.info(
            "Structured Claude request completed | schema=%s",
            output_model.__name__,
        )

        return parsed_output