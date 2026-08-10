import json
from collections.abc import Callable

import httpx
import pytest
from pydantic import BaseModel, Field

from app.services.llm.ollama import OllamaClient, _strip_unsupported_grammar_keywords


class Answer(BaseModel):
    text: str


class Citation(BaseModel):
    source_id: str = Field(min_length=3, max_length=20)


class ConstrainedAnswer(BaseModel):
    text: str = Field(min_length=3, max_length=2_000)
    citations: list[Citation] = Field(default_factory=list, max_length=10)


def make_client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    model: str | None = None,
) -> OllamaClient:
    """Build a real OllamaClient with its HTTP transport swapped for a fake."""

    client = OllamaClient(model=model)
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
        return httpx.Response(
            200,
            json={
                "response": "epoll observes file descriptors.",
                "prompt_eval_count": 12,
                "eval_count": 7,
            },
        )

    client = make_client(handler)

    result = await client.generate_text("Explain epoll.")

    assert result == "epoll observes file descriptors."
    assert calls == 1
    assert client.usage.input_tokens == 12
    assert client.usage.output_tokens == 7
    assert client.usage.request_count == 1


@pytest.mark.anyio
async def test_generate_text_enables_thinking() -> None:
    captured_bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "thinking": "epoll is a Linux syscall for scalable I/O event notification.",
                "response": "epoll observes file descriptors.",
            },
        )

    client = make_client(handler)

    result = await client.generate_text("Explain epoll.")

    assert result == "epoll observes file descriptors."
    assert captured_bodies[0]["think"] is True


@pytest.mark.anyio
async def test_generate_text_raises_when_the_token_budget_is_spent_on_thinking() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"thinking": "Still reasoning about the answer...", "response": ""},
        )

    client = make_client(handler)

    with pytest.raises(RuntimeError, match="used the token budget for reasoning"):
        await client.generate_text("Explain epoll.")


@pytest.mark.anyio
async def test_generate_structured_enables_thinking() -> None:
    captured_bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"response": '{"text": "epoll"}'})

    client = make_client(handler)

    result = await client.generate_structured("Explain epoll.", Answer)

    assert result == Answer(text="epoll")
    assert captured_bodies[0]["think"] is True


@pytest.mark.anyio
async def test_generate_text_uses_the_overridden_model_when_given() -> None:
    captured_bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"response": "epoll observes file descriptors."})

    client = make_client(handler, model="deepseek-r1:14b")

    await client.generate_text("Explain epoll.")

    assert captured_bodies[0]["model"] == "deepseek-r1:14b"


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


def test_strip_unsupported_grammar_keywords_removes_string_length_bounds() -> None:
    schema = ConstrainedAnswer.model_json_schema()
    assert "minLength" in json.dumps(schema)
    assert "maxLength" in json.dumps(schema)

    sanitized = _strip_unsupported_grammar_keywords(schema)

    assert "minLength" not in json.dumps(sanitized)
    assert "maxLength" not in json.dumps(sanitized)
    # Everything else -- structure, $defs/$ref, array maxItems, required --
    # must survive untouched so the grammar hint stays otherwise accurate.
    assert sanitized["properties"]["text"]["type"] == "string"
    assert sanitized["required"] == schema["required"]
    assert sanitized["properties"]["citations"]["maxItems"] == 10
    assert sanitized["$defs"]["Citation"]["properties"]["source_id"]["type"] == "string"
    assert "minLength" not in sanitized["$defs"]["Citation"]["properties"]["source_id"]


@pytest.mark.anyio
async def test_generate_structured_sends_a_sanitized_format_schema() -> None:
    captured_bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"response": '{"text": "epoll", "citations": []}'})

    client = make_client(handler)

    result = await client.generate_structured("Explain epoll.", ConstrainedAnswer)

    assert result == ConstrainedAnswer(text="epoll", citations=[])
    sent_format = captured_bodies[0]["format"]
    assert "minLength" not in json.dumps(sent_format)
    assert "maxLength" not in json.dumps(sent_format)
    # The prompt text keeps the full schema (length bounds included) as
    # guidance -- only the strict "format" grammar needs sanitizing.
    sent_prompt = captured_bodies[0]["prompt"]
    assert isinstance(sent_prompt, str)
    assert "minLength" in sent_prompt
    assert "maxLength" in sent_prompt
