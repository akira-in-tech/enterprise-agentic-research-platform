import json
from typing import cast

import httpx
import pytest

from app.services.embeddings.ollama import (
    OllamaEmbeddingClient,
)


@pytest.mark.anyio
async def test_embed_texts_sends_batch_and_returns_vectors() -> None:
    requests: list[httpx.Request] = []

    def handle_request(
        request: httpx.Request,
    ) -> httpx.Response:
        requests.append(request)

        return httpx.Response(
            200,
            json={
                "model": "qwen3-embedding:0.6b",
                "embeddings": [
                    [0.1, 0.2, 0.3],
                    [0.4, 0.5, 0.6],
                ],
            },
        )

    client = OllamaEmbeddingClient(
        base_url="http://ollama.test",
        model="qwen3-embedding:0.6b",
        dimensions=3,
        transport=httpx.MockTransport(handle_request),
    )

    try:
        vectors = await client.embed_texts(
            [
                "Explain DNS recursive resolution.",
                "Compare HTTP/2 and HTTP/3.",
            ]
        )
    finally:
        await client.close()

    assert vectors == [
        [0.1, 0.2, 0.3],
        [0.4, 0.5, 0.6],
    ]
    assert len(requests) == 1
    assert requests[0].url.path == "/api/embed"

    request_data = cast(
        dict[str, object],
        json.loads(requests[0].content),
    )

    assert request_data == {
        "model": "qwen3-embedding:0.6b",
        "input": [
            "Explain DNS recursive resolution.",
            "Compare HTTP/2 and HTTP/3.",
        ],
        "truncate": False,
        "dimensions": 3,
    }


@pytest.mark.anyio
async def test_empty_batch_does_not_call_ollama() -> None:
    def handle_request(
        request: httpx.Request,
    ) -> httpx.Response:
        pytest.fail(f"Unexpected request to {request.url}.")

    client = OllamaEmbeddingClient(
        base_url="http://ollama.test",
        dimensions=3,
        transport=httpx.MockTransport(handle_request),
    )

    try:
        vectors = await client.embed_texts([])
    finally:
        await client.close()

    assert vectors == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "\n\t",
    ],
)
async def test_embed_texts_rejects_empty_text(
    text: str,
) -> None:
    client = OllamaEmbeddingClient(
        base_url="http://ollama.test",
        dimensions=3,
    )

    try:
        with pytest.raises(
            ValueError,
            match="Embedding text must not be empty",
        ):
            await client.embed_texts([text])
    finally:
        await client.close()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("response_payload", "expected_error"),
    [
        (
            {},
            "did not include an embeddings array",
        ),
        (
            {
                "embeddings": [],
            },
            "returned 0 vectors for 1 inputs",
        ),
        (
            {
                "embeddings": [
                    [0.1, 0.2],
                ],
            },
            "has 2 dimensions; expected 3",
        ),
        (
            {
                "embeddings": [
                    [0.1, True, 0.3],
                ],
            },
            "contains non-numeric values",
        ),
    ],
)
async def test_embed_texts_rejects_invalid_response(
    response_payload: object,
    expected_error: str,
) -> None:
    def handle_request(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            json=response_payload,
            request=request,
        )

    client = OllamaEmbeddingClient(
        base_url="http://ollama.test",
        dimensions=3,
        transport=httpx.MockTransport(handle_request),
    )

    try:
        with pytest.raises(
            RuntimeError,
            match=expected_error,
        ):
            await client.embed_texts(
                [
                    "Explain Linux epoll.",
                ]
            )
    finally:
        await client.close()


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
        OllamaEmbeddingClient(
            dimensions=dimensions,
        )


def test_client_rejects_empty_model() -> None:
    with pytest.raises(
        ValueError,
        match=("Ollama embedding model must not be empty"),
    ):
        OllamaEmbeddingClient(
            model="   ",
        )
