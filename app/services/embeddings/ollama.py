import math
from collections.abc import Sequence
from typing import cast

import httpx

from app.core.config import settings
from app.services.embeddings.base import (
    EmbeddingVector,
)


class OllamaEmbeddingClient:
    """Generate local embeddings through the Ollama HTTP API."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        dimensions: int | None = None,
        timeout_seconds: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        selected_base_url = (base_url if base_url is not None else settings.ollama_base_url).strip()
        selected_model = (model if model is not None else settings.ollama_embedding_model).strip()
        selected_dimensions = (
            dimensions if dimensions is not None else settings.ollama_embedding_dimensions
        )

        if not selected_base_url:
            raise ValueError("Ollama base URL must not be empty.")

        if not selected_model:
            raise ValueError("Ollama embedding model must not be empty.")

        if selected_dimensions < 1:
            raise ValueError("dimensions must be at least 1.")

        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than 0.")

        self._model = selected_model
        self._dimensions = selected_dimensions
        self._client = httpx.AsyncClient(
            base_url=selected_base_url.rstrip("/"),
            timeout=timeout_seconds,
            transport=transport,
        )

    @property
    def dimensions(self) -> int:
        """Return the requested embedding dimensions."""

        return self._dimensions

    async def embed_texts(
        self,
        texts: Sequence[str],
    ) -> list[EmbeddingVector]:
        """Generate one validated vector per input text."""

        normalized_texts = [text.strip() for text in texts]

        if any(not text for text in normalized_texts):
            raise ValueError("Embedding text must not be empty.")

        if not normalized_texts:
            return []

        response = await self._client.post(
            "/api/embed",
            json={
                "model": self._model,
                "input": normalized_texts,
                "truncate": False,
                "dimensions": self._dimensions,
            },
        )
        response.raise_for_status()

        response_data: object = response.json()

        if not isinstance(response_data, dict):
            raise RuntimeError("Ollama returned an invalid embedding response.")

        raw_embeddings = response_data.get("embeddings")

        if not isinstance(raw_embeddings, list):
            raise RuntimeError("Ollama response did not include an embeddings array.")

        if len(raw_embeddings) != len(normalized_texts):
            raise RuntimeError(
                f"Ollama returned {len(raw_embeddings)} vectors for {len(normalized_texts)} inputs."
            )

        vectors: list[EmbeddingVector] = []

        for position, raw_vector in enumerate(raw_embeddings):
            if not isinstance(raw_vector, list):
                raise RuntimeError(f"Ollama embedding vector {position} is not an array.")

            if len(raw_vector) != self._dimensions:
                raise RuntimeError(
                    "Ollama embedding vector "
                    f"{position} has "
                    f"{len(raw_vector)} dimensions; "
                    f"expected {self._dimensions}."
                )

            if any(
                isinstance(value, bool)
                or not isinstance(
                    value,
                    (int, float),
                )
                for value in raw_vector
            ):
                raise RuntimeError(
                    f"Ollama embedding vector {position} contains non-numeric values."
                )

            numeric_values = cast(
                list[int | float],
                raw_vector,
            )
            vector = [float(value) for value in numeric_values]

            if any(not math.isfinite(value) for value in vector):
                raise RuntimeError(
                    f"Ollama embedding vector {position} contains non-finite values."
                )

            vectors.append(vector)

        return vectors

    async def close(self) -> None:
        """Close the underlying HTTP client."""

        await self._client.aclose()
