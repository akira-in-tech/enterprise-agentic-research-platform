import json
from typing import Any, TypeVar, cast

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.core.retry import call_with_backoff

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)

# Only retry connection-level failures (refused/reset/timed-out connections).
# An HTTP status error is either a client bug (4xx, retrying won't help) or a
# local Ollama-side failure unlikely to clear within a couple of retries
# (5xx) -- neither is retried here.
_RETRYABLE_ERRORS = (httpx.TransportError,)

# Ollama compiles the "format" schema into a GBNF grammar (llama.cpp) for
# constrained decoding. That compiler cannot parse minLength/maxLength on
# string fields -- present on every structured-output model in this
# codebase -- and fails the whole request with a 400 "failed to parse
# grammar" before any generation happens. Pydantic still enforces these
# constraints for real once the response comes back
# (model_validate_json below), so dropping them only from the grammar hint
# does not weaken validation.
_UNSUPPORTED_GRAMMAR_KEYWORDS = frozenset({"minLength", "maxLength"})


def _strip_unsupported_grammar_keywords(schema: dict[str, Any]) -> dict[str, Any]:
    """Recursively drop JSON Schema keywords Ollama's grammar compiler rejects."""

    sanitized: dict[str, Any] = {}

    for key, value in schema.items():
        if key in _UNSUPPORTED_GRAMMAR_KEYWORDS:
            continue

        if isinstance(value, dict):
            sanitized[key] = _strip_unsupported_grammar_keywords(value)
        elif isinstance(value, list):
            sanitized[key] = [
                _strip_unsupported_grammar_keywords(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            sanitized[key] = value

    return sanitized


class OllamaClient:
    """Provide local LLM access through the Ollama HTTP API."""

    def __init__(self, *, model: str | None = None) -> None:
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._model = (model or settings.ollama_model).strip()
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=300.0,
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

        async def post_generate() -> httpx.Response:
            response = await self._client.post(
                "/api/generate",
                json={
                    "model": self._model,
                    "prompt": normalized_prompt,
                    "stream": False,
                    "think": True,
                    "options": {
                        "num_predict": max_tokens,
                    },
                },
            )
            response.raise_for_status()
            return response

        response = await call_with_backoff(
            post_generate,
            retryable=_RETRYABLE_ERRORS,
        )

        response_data = cast(dict[str, Any], response.json())
        response_text = str(response_data.get("response") or "").strip()

        if not response_text:
            thinking_text = str(response_data.get("thinking") or "").strip()

            if thinking_text:
                raise RuntimeError(
                    "Ollama used the token budget for reasoning but returned no final text content."
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
        grammar_schema = _strip_unsupported_grammar_keywords(schema)

        structured_prompt = (
            f"{prompt}\n\nReturn only valid JSON matching this JSON schema:\n{json.dumps(schema)}"
        )

        async def post_generate() -> httpx.Response:
            response = await self._client.post(
                "/api/generate",
                json={
                    "model": self._model,
                    "prompt": structured_prompt,
                    "stream": False,
                    "think": True,
                    "format": grammar_schema,
                    "options": {
                        "num_predict": max_tokens,
                    },
                },
            )
            response.raise_for_status()
            return response

        response = await call_with_backoff(
            post_generate,
            retryable=_RETRYABLE_ERRORS,
        )

        raw_text = response.json().get("response", "").strip()

        if not raw_text:
            raise RuntimeError("Ollama returned no structured output.")

        try:
            return output_model.model_validate_json(raw_text)
        except ValidationError as error:
            raise RuntimeError("Ollama returned invalid structured output.") from error

    async def close(self) -> None:
        """Close the underlying HTTP client."""

        await self._client.aclose()
