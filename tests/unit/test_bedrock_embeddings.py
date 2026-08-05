import json
import math
from typing import cast

import pytest

from app.services.embeddings.bedrock import BedrockTitanEmbeddingClient


class RecordingBody:
    def __init__(self, payload: object) -> None:
        self._payload = json.dumps(payload).encode()
        self.closed = False

    def read(self) -> bytes:
        return self._payload

    def close(self) -> None:
        self.closed = True


class RecordingBedrockClient:
    def __init__(self, payloads: list[object]) -> None:
        self._payloads = payloads
        self.calls: list[dict[str, object]] = []
        self.bodies: list[RecordingBody] = []
        self.closed = False

    def invoke_model(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        body = RecordingBody(self._payloads.pop(0))
        self.bodies.append(body)
        return {"body": body}

    def close(self) -> None:
        self.closed = True


@pytest.mark.anyio
async def test_bedrock_embeddings_send_titan_request_and_close_bodies() -> None:
    runtime = RecordingBedrockClient(
        [
            {"embedding": [0.1] * 256},
            {"embedding": [0.2] * 256},
        ]
    )
    client = BedrockTitanEmbeddingClient(
        client=runtime,
        region_name="us-west-2",
        model="amazon.titan-embed-text-v2:0",
        dimensions=256,
    )

    vectors = await client.embed_texts([" first ", "second"])
    await client.close()

    assert vectors == [[0.1] * 256, [0.2] * 256]
    assert runtime.closed is False
    assert all(body.closed for body in runtime.bodies)
    first_call = runtime.calls[0]
    assert first_call["modelId"] == "amazon.titan-embed-text-v2:0"
    assert first_call["contentType"] == "application/json"
    assert first_call["accept"] == "application/json"
    assert json.loads(cast(str, first_call["body"])) == {
        "inputText": "first",
        "dimensions": 256,
        "normalize": True,
        "embeddingTypes": ["float"],
    }


@pytest.mark.anyio
async def test_bedrock_embeddings_empty_batch_does_not_call_runtime() -> None:
    runtime = RecordingBedrockClient([])
    client = BedrockTitanEmbeddingClient(client=runtime, dimensions=256)

    assert await client.embed_texts([]) == []
    assert runtime.calls == []


@pytest.mark.anyio
@pytest.mark.parametrize("text", ["", "  ", "x" * 50_001])
async def test_bedrock_embeddings_reject_invalid_input(text: str) -> None:
    runtime = RecordingBedrockClient([])
    client = BedrockTitanEmbeddingClient(client=runtime, dimensions=256)

    with pytest.raises(ValueError):
        await client.embed_texts([text])

    assert runtime.calls == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    "embedding",
    [[0.1] * 255, [0.1, True] + [0.3] * 254, [math.inf] + [0.3] * 255],
)
async def test_bedrock_embeddings_reject_invalid_vectors_and_close_body(
    embedding: list[object],
) -> None:
    runtime = RecordingBedrockClient([{"embedding": embedding}])
    client = BedrockTitanEmbeddingClient(client=runtime, dimensions=256)

    with pytest.raises(RuntimeError, match="embedding"):
        await client.embed_texts(["trusted evidence"])

    assert runtime.bodies[0].closed is True


@pytest.mark.parametrize("dimensions", [0, 128, 2048])
def test_bedrock_embeddings_reject_unsupported_dimensions(dimensions: int) -> None:
    with pytest.raises(ValueError, match="256, 512, or 1024"):
        BedrockTitanEmbeddingClient(
            client=RecordingBedrockClient([]),
            dimensions=dimensions,
        )
