from collections.abc import Awaitable
from unittest.mock import Mock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.services.cache import (
    RedisConnection,
    RedisUnavailableError,
)
from app.services.cache import redis as redis_module


class FakeAsyncRedisClient:
    def __init__(
        self,
        *,
        ping_result: bool = True,
        ping_error: RedisConnectionError | None = None,
    ) -> None:
        self.ping_result = ping_result
        self.ping_error = ping_error
        self.ping_calls = 0
        self.close_calls = 0

    def ping(self) -> Awaitable[bool]:
        async def execute_ping() -> bool:
            self.ping_calls += 1

            if self.ping_error is not None:
                raise self.ping_error

            return self.ping_result

        return execute_ping()

    async def aclose(
        self,
        close_connection_pool: bool | None = None,
    ) -> None:
        del close_connection_pool
        self.close_calls += 1


def test_from_url_configures_async_redis_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_client = FakeAsyncRedisClient()
    from_url = Mock(
        return_value=raw_client,
    )
    monkeypatch.setattr(
        redis_module,
        "_create_redis_client",
        from_url,
    )

    connection = RedisConnection.from_url(
        url="redis://cache.internal:6380/2",
        max_connections=48,
        socket_connect_timeout_seconds=1.5,
        socket_timeout_seconds=3.0,
        health_check_interval_seconds=15,
    )

    assert isinstance(
        connection,
        RedisConnection,
    )
    from_url.assert_called_once_with(
        "redis://cache.internal:6380/2",
        max_connections=48,
        socket_connect_timeout_seconds=1.5,
        socket_timeout_seconds=3.0,
        health_check_interval_seconds=15,
    )


@pytest.mark.anyio
async def test_ping_returns_true_when_redis_is_available() -> None:
    raw_client = FakeAsyncRedisClient(
        ping_result=True,
    )
    connection = RedisConnection(
        raw_client,
    )

    assert await connection.ping() is True
    assert raw_client.ping_calls == 1


@pytest.mark.anyio
async def test_ping_preserves_false_health_response() -> None:
    raw_client = FakeAsyncRedisClient(
        ping_result=False,
    )
    connection = RedisConnection(
        raw_client,
    )

    assert await connection.ping() is False
    assert raw_client.ping_calls == 1


@pytest.mark.anyio
async def test_ping_wraps_redis_connection_error() -> None:
    raw_client = FakeAsyncRedisClient(
        ping_error=RedisConnectionError("Redis refused the connection."),
    )
    connection = RedisConnection(
        raw_client,
    )

    with pytest.raises(
        RedisUnavailableError,
        match="Redis health check failed",
    ):
        await connection.ping()


@pytest.mark.anyio
async def test_close_closes_underlying_client() -> None:
    raw_client = FakeAsyncRedisClient()
    connection = RedisConnection(
        raw_client,
    )

    await connection.close()

    assert raw_client.close_calls == 1


def test_from_url_rejects_empty_url() -> None:
    with pytest.raises(
        ValueError,
        match="Redis URL must not be empty",
    ):
        RedisConnection.from_url(
            url="   ",
        )


def test_from_url_rejects_empty_connection_pool() -> None:
    with pytest.raises(
        ValueError,
        match="max_connections must be at least 1",
    ):
        RedisConnection.from_url(
            max_connections=0,
        )


def test_from_url_rejects_invalid_connect_timeout() -> None:
    with pytest.raises(
        ValueError,
        match="socket_connect_timeout_seconds must be greater than 0",
    ):
        RedisConnection.from_url(
            socket_connect_timeout_seconds=0,
        )


def test_from_url_rejects_invalid_socket_timeout() -> None:
    with pytest.raises(
        ValueError,
        match="socket_timeout_seconds must be greater than 0",
    ):
        RedisConnection.from_url(
            socket_timeout_seconds=0,
        )


def test_from_url_rejects_negative_health_check_interval() -> None:
    with pytest.raises(
        ValueError,
        match="health_check_interval_seconds must not be negative",
    ):
        RedisConnection.from_url(
            health_check_interval_seconds=-1,
        )
