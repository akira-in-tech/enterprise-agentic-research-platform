import logging

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.core.correlation import (
    CorrelationIdLogFilter,
    CorrelationIdMiddleware,
    _is_valid_client_correlation_id,
    get_correlation_id,
)


async def echo_correlation_id(_: Request) -> PlainTextResponse:
    return PlainTextResponse(get_correlation_id() or "missing")


def build_client() -> TestClient:
    app = Starlette(routes=[Route("/echo", echo_correlation_id)])
    app.add_middleware(CorrelationIdMiddleware)
    return TestClient(app)


def test_generates_a_correlation_id_when_none_is_supplied() -> None:
    client = build_client()

    response = client.get("/echo")

    correlation_id = response.headers["x-correlation-id"]
    assert correlation_id
    assert response.text == correlation_id


def test_echoes_a_valid_client_supplied_correlation_id() -> None:
    client = build_client()

    response = client.get("/echo", headers={"x-correlation-id": "trace-abc-123"})

    assert response.headers["x-correlation-id"] == "trace-abc-123"
    assert response.text == "trace-abc-123"


def test_replaces_an_overlong_client_supplied_correlation_id() -> None:
    client = build_client()
    overlong = "a" * 500

    response = client.get("/echo", headers={"x-correlation-id": overlong})

    assert response.headers["x-correlation-id"] != overlong
    assert response.text == response.headers["x-correlation-id"]


def test_correlation_id_is_cleared_after_the_request_completes() -> None:
    client = build_client()

    client.get("/echo")

    assert get_correlation_id() is None


def test_is_valid_client_correlation_id_rejects_control_characters() -> None:
    assert _is_valid_client_correlation_id("safe-id") is True
    assert _is_valid_client_correlation_id("") is False
    assert _is_valid_client_correlation_id("bad\nvalue") is False
    assert _is_valid_client_correlation_id("a" * 500) is False


def test_log_filter_injects_dash_outside_a_request_context() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="message",
        args=(),
        exc_info=None,
    )

    assert CorrelationIdLogFilter().filter(record) is True
    assert record.correlation_id == "-"  # type: ignore[attr-defined]
