import asyncio
import math

import pytest

from app.services.embeddings.base import (
    EmbeddingClient,
)
from app.services.embeddings.deterministic import (
    DeterministicEmbeddingClient,
)


def test_deterministic_client_matches_embedding_protocol() -> None:
    client: EmbeddingClient = DeterministicEmbeddingClient(
        dimensions=8,
    )

    vectors = asyncio.run(
        client.embed_texts(
            [
                "Explain DNS recursive resolution.",
            ]
        )
    )

    assert client.dimensions == 8
    assert len(vectors) == 1
    assert len(vectors[0]) == 8


def test_embeddings_are_deterministic() -> None:
    texts = [
        "Explain DNS recursive resolution.",
        "Compare HTTP/2 and HTTP/3.",
    ]

    first_client = DeterministicEmbeddingClient(
        dimensions=12,
    )
    second_client = DeterministicEmbeddingClient(
        dimensions=12,
    )

    first_vectors = asyncio.run(first_client.embed_texts(texts))
    second_vectors = asyncio.run(second_client.embed_texts(texts))

    assert first_vectors == second_vectors
    assert first_vectors[0] != first_vectors[1]


def test_embeddings_preserve_input_order() -> None:
    client = DeterministicEmbeddingClient(
        dimensions=8,
    )

    forward = asyncio.run(
        client.embed_texts(
            [
                "PostgreSQL indexing",
                "Redis persistence",
            ]
        )
    )
    reversed_vectors = asyncio.run(
        client.embed_texts(
            [
                "Redis persistence",
                "PostgreSQL indexing",
            ]
        )
    )

    assert forward == list(reversed(reversed_vectors))


def test_embeddings_are_unit_length() -> None:
    client = DeterministicEmbeddingClient(
        dimensions=16,
    )

    vectors = asyncio.run(
        client.embed_texts(
            [
                "How does Linux epoll work?",
            ]
        )
    )

    magnitude = math.sqrt(sum(value * value for value in vectors[0]))

    assert magnitude == pytest.approx(1.0)


def test_empty_batch_returns_empty_list() -> None:
    client = DeterministicEmbeddingClient()

    vectors = asyncio.run(client.embed_texts([]))

    assert vectors == []


@pytest.mark.parametrize(
    "dimensions",
    [
        0,
        -1,
    ],
)
def test_client_rejects_invalid_dimensions(
    dimensions: int,
) -> None:
    with pytest.raises(
        ValueError,
        match="dimensions must be at least 1",
    ):
        DeterministicEmbeddingClient(
            dimensions=dimensions,
        )


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "\n\t",
    ],
)
def test_client_rejects_empty_text(
    text: str,
) -> None:
    client = DeterministicEmbeddingClient()

    with pytest.raises(
        ValueError,
        match="Embedding text must not be empty",
    ):
        asyncio.run(client.embed_texts([text]))
