from collections.abc import Callable

import httpx
import pytest
from pydantic import BaseModel

from app.services.llm.ollama import OllamaClient


class Answer(BaseModel):
    text: str


def make_client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> OllamaClient:
    """Build a real OllamaClient with its HTTP transport swapped for a fake."""

    client = OllamaClient()
    client._client = httpx.AsyncClient(
        base_url=client._client.base_url,
        transport=httpx.MockTransport(handler),
    )
    return client


@pytest.mark.anyio
async def test_generate_text_succeeds_on_first_attempt() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"response": "epoll observes file descriptors."})

    client = make_client(handler)

    result = await client.generate_text("Explain epoll.")

    assert result == "epoll observes file descriptors."
    assert calls == 1


@pytest.mark.anyio
async def test_generate_text_retries_a_connection_error() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1

        if calls == 1:
            raise httpx.ConnectError("Connection refused.", request=request)

        return httpx.Response(200, json={"response": "epoll observes file descriptors."})

    client = make_client(handler)

    result = await client.generate_text("Explain epoll.")

    assert result == "epoll observes file descriptors."
    assert calls == 2


@pytest.mark.anyio
async def test_generate_text_does_not_retry_a_client_error() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, json={"error": "bad request"})

    client = make_client(handler)

    with pytest.raises(httpx.HTTPStatusError):
        await client.generate_text("Explain epoll.")

    assert calls == 1


@pytest.mark.anyio
async def test_generate_structured_retries_a_connection_error() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1

        if calls == 1:
            raise httpx.ConnectError("Connection refused.", request=request)

        return httpx.Response(200, json={"response": '{"text": "epoll"}'})

    client = make_client(handler)

    result = await client.generate_structured("Explain epoll.", Answer)

    assert result == Answer(text="epoll")
    assert calls == 2
