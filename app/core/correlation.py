import logging
import uuid
from contextvars import ContextVar

from starlette.types import ASGIApp, Message, Receive, Scope, Send

CORRELATION_ID_HEADER = b"x-correlation-id"
MAX_CORRELATION_ID_LENGTH = 200

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def get_correlation_id() -> str | None:
    """Return the correlation ID for the request currently being handled."""

    return _correlation_id.get()


def _is_valid_client_correlation_id(value: str) -> bool:
    normalized = value.strip()

    return 0 < len(normalized) <= MAX_CORRELATION_ID_LENGTH and normalized.isprintable()


class CorrelationIdMiddleware:
    """Attach a stable per-request correlation ID to context, logs, and the response.

    Reuses a caller-supplied X-Correlation-ID when it looks safe to log and
    echo back; otherwise generates a new one. This lets a client trace one
    logical request across services while preventing header values with
    control characters or unbounded length from reaching log output.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        incoming = headers.get(CORRELATION_ID_HEADER)
        candidate = incoming.decode("latin-1") if incoming is not None else ""
        correlation_id = (
            candidate.strip() if _is_valid_client_correlation_id(candidate) else str(uuid.uuid4())
        )

        token = _correlation_id.set(correlation_id)

        async def send_with_correlation_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers") or [])
                response_headers.append(
                    (CORRELATION_ID_HEADER, correlation_id.encode("latin-1"))
                )
                message = {**message, "headers": response_headers}

            await send(message)

        try:
            await self._app(scope, receive, send_with_correlation_id)
        finally:
            _correlation_id.reset(token)


class CorrelationIdLogFilter(logging.Filter):
    """Inject the active request's correlation ID into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id() or "-"
        return True
