import asyncio
import json
import math
from collections.abc import Sequence
from typing import Protocol, cast

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]

from app.core.config import settings
from app.services.embeddings.base import EmbeddingVector


class BedrockResponseBody(Protocol):
    def read(self) -> bytes: ...

    def close(self) -> None: ...


class BedrockRuntimeClient(Protocol):
    def invoke_model(self, **kwargs: object) -> dict[str, object]: ...

    def close(self) -> None: ...


def create_bedrock_runtime_client(*, region_name: str) -> BedrockRuntimeClient:
    """Create one reusable Bedrock Runtime client with bounded adaptive retries."""

    return cast(
        BedrockRuntimeClient,
        boto3.client(
            "bedrock-runtime",
            region_name=region_name,
            config=Config(
                retries={"total_max_attempts": 5, "mode": "adaptive"},
                connect_timeout=5,
                read_timeout=30,
                max_pool_connections=20,
            ),
        ),
    )


class BedrockTitanEmbeddingClient:
    """Generate normalized embeddings with Amazon Titan Text Embeddings V2."""

    def __init__(
        self,
        *,
        client: BedrockRuntimeClient | None = None,
        region_name: str | None = None,
        model: str | None = None,
        dimensions: int | None = None,
    ) -> None:
        selected_region = (region_name or settings.aws_region).strip()
        selected_model = (model or settings.bedrock_embedding_model).strip()
        selected_dimensions = (
            dimensions if dimensions is not None else settings.bedrock_embedding_dimensions
        )

        if not selected_region:
            raise ValueError("AWS region must not be empty.")
        if not selected_model:
            raise ValueError("Bedrock embedding model must not be empty.")
        if selected_dimensions not in {256, 512, 1024}:
            raise ValueError("Titan embedding dimensions must be 256, 512, or 1024.")

        self._client = client or create_bedrock_runtime_client(region_name=selected_region)
        self._owns_client = client is None
        self._model = selected_model
        self._dimensions = selected_dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed_texts(self, texts: Sequence[str]) -> list[EmbeddingVector]:
        normalized_texts = [text.strip() for text in texts]
        if any(not text for text in normalized_texts):
            raise ValueError("Embedding text must not be empty.")
        if any(len(text) > 50_000 for text in normalized_texts):
            raise ValueError("Titan embedding input must not exceed 50,000 characters.")

        vectors: list[EmbeddingVector] = []
        for text in normalized_texts:
            vectors.append(await asyncio.to_thread(self._embed_one, text))
        return vectors

    def _embed_one(self, text: str) -> EmbeddingVector:
        response = self._client.invoke_model(
            modelId=self._model,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(
                {
                    "inputText": text,
                    "dimensions": self._dimensions,
                    "normalize": True,
                    "embeddingTypes": ["float"],
                }
            ),
        )
        body = response.get("body")
        if body is None or not hasattr(body, "read") or not hasattr(body, "close"):
            raise RuntimeError("Bedrock returned an invalid response body.")

        stream = cast(BedrockResponseBody, body)
        try:
            payload: object = json.loads(stream.read())
        finally:
            stream.close()

        if not isinstance(payload, dict):
            raise RuntimeError("Bedrock returned an invalid embedding response.")
        raw_embedding = payload.get("embedding")
        if not isinstance(raw_embedding, list) or len(raw_embedding) != self._dimensions:
            raise RuntimeError(f"Bedrock embedding must contain exactly {self._dimensions} values.")
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            for value in raw_embedding
        ):
            raise RuntimeError("Bedrock embedding contains non-numeric values.")

        numeric_values = cast(list[int | float], raw_embedding)
        vector = [float(value) for value in numeric_values]
        if any(not math.isfinite(value) for value in vector):
            raise RuntimeError("Bedrock embedding contains non-finite values.")
        return vector

    async def close(self) -> None:
        if self._owns_client:
            await asyncio.to_thread(self._client.close)
