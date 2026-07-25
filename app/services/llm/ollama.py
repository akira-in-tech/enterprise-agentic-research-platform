import json
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import settings

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class OllamaClient:
    """Provide local LLM access through the Ollama HTTP API."""

    def __init__(self) -> None:
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._model = settings.ollama_model
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=60.0,
        )

    async def generate_text(
        self,
        prompt: str,
        *,
        max_tokens: int = 64,
    ) -> str:
        """Generate an unstructured text response from Ollama."""

        normalized_prompt = prompt.strip()

        if not normalized_prompt:
            raise ValueError("Prompt must not be empty.")

        response = await self._client.post(
            "/api/generate",
            json={
                "model": self._model,
                "prompt": normalized_prompt,
                "stream": False,
                "think": False,
                "options": {
                    "num_predict": max_tokens,
                },
            },
        )
        response.raise_for_status()

        response_data = response.json()
        response_text = response_data.get("response", "").strip()

        if not response_text:
            thinking_text = response_data.get("thinking", "").strip()

            if thinking_text:
                raise RuntimeError(
                    "Ollama used the token budget for reasoning but returned "
                    "no final text content."
                )

            raise RuntimeError("Ollama returned no text content.")

        return response_text

    async def generate_structured(
        self,
        prompt: str,
        output_model: type[StructuredModel],
        *,
        max_tokens: int = 256,
    ) -> StructuredModel:
        """Generate JSON and validate it against a Pydantic model."""

        schema = output_model.model_json_schema()

        structured_prompt = (
            f"{prompt}\n\n"
            "Return only valid JSON matching this JSON schema:\n"
            f"{json.dumps(schema)}"
        )

        response = await self._client.post(
            "/api/generate",
            json={
                "model": self._model,
                "prompt": structured_prompt,
                "stream": False,
                "think": False,
                "format": schema,
                "options": {
                    "num_predict": max_tokens,
                },
            },
        )
        response.raise_for_status()

        raw_text = response.json().get("response", "").strip()

        if not raw_text:
            raise RuntimeError("Ollama returned no structured output.")

        try:
            return output_model.model_validate_json(raw_text)
        except ValidationError as error:
            raise RuntimeError(
                "Ollama returned invalid structured output."
            ) from error

    async def close(self) -> None:
        """Close the underlying HTTP client."""

        await self._client.aclose()