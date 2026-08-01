from collections.abc import Awaitable
from unittest.mock import Mock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.services.cache import (
    CacheUnavailableError,
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
        get_result: str | None = None,
        set_result: bool | None = True,
        delete_result: int = 1,
        ttl_result: int = 900,
        operation_error: RedisConnectionError | None = None,
        eval_result: object = 1,
    ) -> None:
        self.ping_result = ping_result
        self.ping_error = ping_error
        self.get_result = get_result
        self.set_result = set_result
        self.delete_result = delete_result
        self.ttl_result = ttl_result
        self.operation_error = operation_error
        self.eval_result = eval_result
        self.eval_calls: list[tuple[str, int, tuple[str, ...]]] = []
        self.ping_calls = 0
        self.get_calls: list[str] = []
        self.set_calls: list[tuple[str, str, int, bool]] = []
        self.delete_calls: list[str] = []
        self.ttl_calls: list[str] = []
        self.close_calls = 0

    def _raise_operation_error(self) -> None:
        if self.operation_error is not None:
            raise self.operation_error

    def ping(self) -> Awaitable[bool]:
        async def execute_ping() -> bool:
            self.ping_calls += 1

            if self.ping_error is not None:
                raise self.ping_error

            return self.ping_result

        return execute_ping()

    async def get(
        self,
        name: str,
    ) -> str | None:
        self.get_calls.append(name)
        self._raise_operation_error()

        return self.get_result

    async def set(
        self,
        name: str,
        value: str,
        *,
        ex: int,
        nx: bool = False,
    ) -> bool | None:
        self.set_calls.append(
            (
                name,
                value,
                ex,
                nx,
            )
        )
        self._raise_operation_error()

        return self.set_result

    async def delete(
        self,
        *names: str,
    ) -> int:
        self.delete_calls.extend(
            names,
        )
        self._raise_operation_error()

        return self.delete_result

    async def ttl(
        self,
        name: str,
    ) -> int:
        self.ttl_calls.append(name)
        self._raise_operation_error()

        return self.ttl_result

    async def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: str,
    ) -> object:
        self.eval_calls.append(
            (
                script,
                numkeys,
                keys_and_args,
            )
        )
        self._raise_operation_error()

        return self.eval_result

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


@pytest.mark.anyio
async def test_get_text_returns_cached_value() -> None:
    raw_client = FakeAsyncRedisClient(
        get_result='{"status":"completed"}',
    )
    connection = RedisConnection(
        raw_client,
    )

    result = await connection.get_text(
        key="enterprise-research:v1:test",
    )

    assert result == '{"status":"completed"}'
    assert raw_client.get_calls == [
        "enterprise-research:v1:test",
    ]


@pytest.mark.anyio
async def test_get_text_returns_none_for_cache_miss() -> None:
    raw_client = FakeAsyncRedisClient(
        get_result=None,
    )
    connection = RedisConnection(
        raw_client,
    )

    result = await connection.get_text(
        key="enterprise-research:v1:missing",
    )

    assert result is None


@pytest.mark.anyio
async def test_set_text_writes_value_with_ttl() -> None:
    raw_client = FakeAsyncRedisClient(
        set_result=True,
    )
    connection = RedisConnection(
        raw_client,
    )

    await connection.set_text(
        key="enterprise-research:v1:test",
        value='{"status":"completed"}',
        ttl_seconds=900,
    )

    assert raw_client.set_calls == [
        (
            "enterprise-research:v1:test",
            '{"status":"completed"}',
            900,
            False,
        )
    ]


@pytest.mark.anyio
async def test_set_text_rejects_unconfirmed_write() -> None:
    raw_client = FakeAsyncRedisClient(
        set_result=None,
    )
    connection = RedisConnection(
        raw_client,
    )

    with pytest.raises(
        RedisUnavailableError,
        match="did not confirm the write",
    ):
        await connection.set_text(
            key="enterprise-research:v1:test",
            value="value",
            ttl_seconds=900,
        )


@pytest.mark.anyio
async def test_delete_returns_true_for_existing_key() -> None:
    raw_client = FakeAsyncRedisClient(
        delete_result=1,
    )
    connection = RedisConnection(
        raw_client,
    )

    deleted = await connection.delete(
        key="enterprise-research:v1:test",
    )

    assert deleted is True
    assert raw_client.delete_calls == [
        "enterprise-research:v1:test",
    ]


@pytest.mark.anyio
async def test_delete_returns_false_for_missing_key() -> None:
    raw_client = FakeAsyncRedisClient(
        delete_result=0,
    )
    connection = RedisConnection(
        raw_client,
    )

    deleted = await connection.delete(
        key="enterprise-research:v1:missing",
    )

    assert deleted is False


@pytest.mark.anyio
async def test_ttl_seconds_returns_redis_ttl() -> None:
    raw_client = FakeAsyncRedisClient(
        ttl_result=842,
    )
    connection = RedisConnection(
        raw_client,
    )

    ttl = await connection.ttl_seconds(
        key="enterprise-research:v1:test",
    )

    assert ttl == 842
    assert raw_client.ttl_calls == [
        "enterprise-research:v1:test",
    ]


@pytest.mark.anyio
async def test_get_text_wraps_redis_error() -> None:
    raw_client = FakeAsyncRedisClient(
        operation_error=RedisConnectionError("Redis connection was lost."),
    )
    connection = RedisConnection(
        raw_client,
    )

    with pytest.raises(
        RedisUnavailableError,
        match="Redis GET failed",
    ):
        await connection.get_text(
            key="enterprise-research:v1:test",
        )


@pytest.mark.anyio
async def test_text_commands_reject_blank_key() -> None:
    connection = RedisConnection(
        FakeAsyncRedisClient(),
    )

    with pytest.raises(
        ValueError,
        match="Redis key must not be empty",
    ):
        await connection.get_text(
            key="   ",
        )


@pytest.mark.anyio
async def test_set_text_rejects_non_positive_ttl() -> None:
    connection = RedisConnection(
        FakeAsyncRedisClient(),
    )

    with pytest.raises(
        ValueError,
        match="ttl_seconds must be at least 1",
    ):
        await connection.set_text(
            key="enterprise-research:v1:test",
            value="value",
            ttl_seconds=0,
        )


def test_redis_unavailable_error_is_cache_error() -> None:
    assert issubclass(
        RedisUnavailableError,
        CacheUnavailableError,
    )


@pytest.mark.anyio
async def test_set_if_absent_returns_true_when_key_is_created() -> None:
    raw_client = FakeAsyncRedisClient(
        set_result=True,
    )
    connection = RedisConnection(
        raw_client,
    )

    acquired = await connection.set_if_absent(
        key="enterprise-research:v1:lock",
        value="owner-token",
        ttl_seconds=120,
    )

    assert acquired is True
    assert raw_client.set_calls == [
        (
            "enterprise-research:v1:lock",
            "owner-token",
            120,
            True,
        )
    ]


@pytest.mark.anyio
async def test_set_if_absent_returns_false_when_key_exists() -> None:
    connection = RedisConnection(
        FakeAsyncRedisClient(
            set_result=None,
        ),
    )

    acquired = await connection.set_if_absent(
        key="enterprise-research:v1:lock",
        value="owner-token",
        ttl_seconds=120,
    )

    assert acquired is False


@pytest.mark.anyio
async def test_set_if_absent_rejects_non_positive_ttl() -> None:
    connection = RedisConnection(
        FakeAsyncRedisClient(),
    )

    with pytest.raises(
        ValueError,
        match="ttl_seconds must be at least 1",
    ):
        await connection.set_if_absent(
            key="enterprise-research:v1:lock",
            value="owner-token",
            ttl_seconds=0,
        )


@pytest.mark.anyio
async def test_set_if_absent_wraps_redis_error() -> None:
    connection = RedisConnection(
        FakeAsyncRedisClient(
            operation_error=RedisConnectionError("Redis connection was lost."),
        ),
    )

    with pytest.raises(
        RedisUnavailableError,
        match="Redis SET NX failed",
    ):
        await connection.set_if_absent(
            key="enterprise-research:v1:lock",
            value="owner-token",
            ttl_seconds=120,
        )


@pytest.mark.anyio
async def test_delete_if_value_deletes_matching_value() -> None:
    raw_client = FakeAsyncRedisClient(
        eval_result=1,
    )
    connection = RedisConnection(
        raw_client,
    )

    deleted = await connection.delete_if_value(
        key="enterprise-research:v1:lock",
        expected_value="owner-token",
    )

    assert deleted is True

    script, numkeys, keys_and_args = raw_client.eval_calls[0]

    assert 'redis.call("GET", KEYS[1])' in script
    assert 'redis.call("DEL", KEYS[1])' in script
    assert numkeys == 1
    assert keys_and_args == (
        "enterprise-research:v1:lock",
        "owner-token",
    )


@pytest.mark.anyio
async def test_delete_if_value_preserves_non_matching_value() -> None:
    connection = RedisConnection(
        FakeAsyncRedisClient(
            eval_result=0,
        ),
    )

    deleted = await connection.delete_if_value(
        key="enterprise-research:v1:lock",
        expected_value="expired-owner-token",
    )

    assert deleted is False


@pytest.mark.anyio
async def test_delete_if_value_rejects_blank_expected_value() -> None:
    connection = RedisConnection(
        FakeAsyncRedisClient(),
    )

    with pytest.raises(
        ValueError,
        match="expected_value must not be empty",
    ):
        await connection.delete_if_value(
            key="enterprise-research:v1:lock",
            expected_value="   ",
        )


@pytest.mark.anyio
async def test_delete_if_value_wraps_redis_error() -> None:
    connection = RedisConnection(
        FakeAsyncRedisClient(
            operation_error=RedisConnectionError("Redis connection was lost."),
        ),
    )

    with pytest.raises(
        RedisUnavailableError,
        match="compare-and-delete failed",
    ):
        await connection.delete_if_value(
            key="enterprise-research:v1:lock",
            expected_value="owner-token",
        )


@pytest.mark.anyio
async def test_increment_with_ttl_returns_counter_and_expiration() -> None:
    raw_client = FakeAsyncRedisClient(
        eval_result=[
            3,
            42,
        ],
    )
    connection = RedisConnection(
        raw_client,
    )

    result = await connection.increment_with_ttl(
        key="enterprise-research:v1:tenant:test:research-rate-limit",
        ttl_seconds=60,
    )

    assert result == (
        3,
        42,
    )

    script, numkeys, keys_and_args = raw_client.eval_calls[0]

    assert 'redis.call("INCR", KEYS[1])' in script
    assert 'redis.call("EXPIRE", KEYS[1], ARGV[1])' in script
    assert numkeys == 1
    assert keys_and_args == (
        "enterprise-research:v1:tenant:test:research-rate-limit",
        "60",
    )


@pytest.mark.anyio
async def test_increment_with_ttl_rejects_non_positive_ttl() -> None:
    connection = RedisConnection(
        FakeAsyncRedisClient(),
    )

    with pytest.raises(
        ValueError,
        match="ttl_seconds must be at least 1",
    ):
        await connection.increment_with_ttl(
            key="enterprise-research:v1:tenant:test:research-rate-limit",
            ttl_seconds=0,
        )


@pytest.mark.anyio
async def test_increment_with_ttl_rejects_invalid_response() -> None:
    connection = RedisConnection(
        FakeAsyncRedisClient(
            eval_result="invalid",
        ),
    )

    with pytest.raises(
        RedisUnavailableError,
        match="invalid response",
    ):
        await connection.increment_with_ttl(
            key="enterprise-research:v1:tenant:test:research-rate-limit",
            ttl_seconds=60,
        )


@pytest.mark.anyio
async def test_increment_with_ttl_wraps_redis_error() -> None:
    connection = RedisConnection(
        FakeAsyncRedisClient(
            operation_error=RedisConnectionError("Redis connection was lost."),
        ),
    )

    with pytest.raises(
        RedisUnavailableError,
        match="rate-limit increment failed",
    ):
        await connection.increment_with_ttl(
            key="enterprise-research:v1:tenant:test:research-rate-limit",
            ttl_seconds=60,
        )
