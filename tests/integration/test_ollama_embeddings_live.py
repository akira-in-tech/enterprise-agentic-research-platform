import math

import httpx
import pytest

from app.core.config import settings
from app.services.embeddings.base import (
    EmbeddingVector,
)
from app.services.embeddings.ollama import (
    OllamaEmbeddingClient,
)


@pytest.mark.integration
@pytest.mark.anyio
async def test_ollama_live_embeddings_are_well_formed() -> None:
    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    client = OllamaEmbeddingClient()
    vectors: list[EmbeddingVector]

    try:
        try:
            vectors = await client.embed_texts(
                [
                    "Explain DNS recursive resolution.",
                    "Compare HTTP/2 and HTTP/3.",
                ]
            )
        except httpx.RequestError as error:
            pytest.fail(
                "Ollama is not reachable. "
                "Start Ollama before running this test. "
                f"Error: {error.__class__.__name__}.",
                pytrace=False,
            )
        except httpx.HTTPStatusError as error:
            pytest.fail(
                "Ollama embedding request failed with "
                f"HTTP {error.response.status_code}. "
                "Confirm that model "
                f"{settings.ollama_embedding_model!r} "
                "has been downloaded.",
                pytrace=False,
            )
    finally:
        await client.close()

    assert len(vectors) == 2

    assert all(len(vector) == settings.ollama_embedding_dimensions for vector in vectors)

    assert all(math.isfinite(value) for vector in vectors for value in vector)

    assert all(any(value != 0.0 for value in vector) for vector in vectors)

    assert vectors[0] != vectors[1]
