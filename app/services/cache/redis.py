from collections.abc import Awaitable
from typing import Protocol, cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.services.cache.base import CacheUnavailableError

_COMPARE_AND_DELETE_SCRIPT = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
end
return 0
""".strip()

_INCREMENT_WITH_TTL_SCRIPT = """
local current = redis.call("INCR", KEYS[1])
if current == 1 then
    redis.call("EXPIRE", KEYS[1], ARGV[1])
end
local remaining_ttl = redis.call("TTL", KEYS[1])
return {current, remaining_ttl}
""".strip()


class AsyncRedisClient(Protocol):
    """Redis operations required by the application wrapper."""

    def ping(self) -> Awaitable[bool]:
        """Return whether Redis is reachable."""

    def get(
        self,
        name: str,
    ) -> Awaitable[str | None]:
        """Return one decoded string value."""

    def set(
        self,
        name: str,
        value: str,
        *,
        ex: int,
        nx: bool = False,
    ) -> Awaitable[bool | None]:
        """Store one string value with expiration."""

    def delete(
        self,
        *names: str,
    ) -> Awaitable[int]:
        """Delete Redis keys."""

    def ttl(
        self,
        name: str,
    ) -> Awaitable[int]:
        """Return the remaining key lifetime."""

    def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: str,
    ) -> Awaitable[object]:
        """Execute one Lua script atomically."""

    async def aclose(
        self,
        close_connection_pool: bool | None = None,
    ) -> None:
        """Close the client and its connection pool."""


def _create_redis_client(
    url: str,
    *,
    max_connections: int,
    socket_connect_timeout_seconds: float,
    socket_timeout_seconds: float,
    health_check_interval_seconds: int,
) -> AsyncRedisClient:
    """Create the concrete redis-py client behind the application protocol."""

    raw_client = Redis.from_url(
        url,
        decode_responses=True,
        max_connections=max_connections,
        socket_connect_timeout=socket_connect_timeout_seconds,
        socket_timeout=socket_timeout_seconds,
        health_check_interval=health_check_interval_seconds,
    )

    return cast(
        AsyncRedisClient,
        raw_client,
    )


def _validate_key(
    key: str,
) -> str:
    """Validate one application-owned Redis key."""

    normalized_key = key.strip()

    if not normalized_key:
        raise ValueError("Redis key must not be empty.")

    if normalized_key != key:
        raise ValueError("Redis key must not contain surrounding whitespace.")

    return key


class RedisUnavailableError(CacheUnavailableError):
    """Raised when Redis cannot complete an infrastructure operation."""


class RedisConnection:
    """Own an asynchronous Redis client and its connection lifecycle."""

    def __init__(
        self,
        client: AsyncRedisClient,
    ) -> None:
        self._client = client

    @classmethod
    def from_url(
        cls,
        *,
        url: str | None = None,
        max_connections: int | None = None,
        socket_connect_timeout_seconds: float | None = None,
        socket_timeout_seconds: float | None = None,
        health_check_interval_seconds: int | None = None,
    ) -> "RedisConnection":
        """Create a Redis connection using explicit values or application settings."""

        selected_url = (url if url is not None else settings.redis_url.get_secret_value()).strip()
        selected_max_connections = (
            max_connections if max_connections is not None else settings.redis_max_connections
        )
        selected_connect_timeout = (
            socket_connect_timeout_seconds
            if socket_connect_timeout_seconds is not None
            else settings.redis_socket_connect_timeout_seconds
        )
        selected_socket_timeout = (
            socket_timeout_seconds
            if socket_timeout_seconds is not None
            else settings.redis_socket_timeout_seconds
        )
        selected_health_check_interval = (
            health_check_interval_seconds
            if health_check_interval_seconds is not None
            else settings.redis_health_check_interval_seconds
        )

        if not selected_url:
            raise ValueError("Redis URL must not be empty.")

        if selected_max_connections < 1:
            raise ValueError("Redis max_connections must be at least 1.")

        if selected_connect_timeout <= 0:
            raise ValueError("Redis socket_connect_timeout_seconds must be greater than 0.")

        if selected_socket_timeout <= 0:
            raise ValueError("Redis socket_timeout_seconds must be greater than 0.")

        if selected_health_check_interval < 0:
            raise ValueError("Redis health_check_interval_seconds must not be negative.")

        client = _create_redis_client(
            selected_url,
            max_connections=selected_max_connections,
            socket_connect_timeout_seconds=selected_connect_timeout,
            socket_timeout_seconds=selected_socket_timeout,
            health_check_interval_seconds=selected_health_check_interval,
        )

        return cls(client)

    async def ping(self) -> bool:
        """Check whether Redis is reachable."""

        try:
            return await self._client.ping()
        except RedisError as error:
            raise RedisUnavailableError("Redis health check failed.") from error

    async def get_text(
        self,
        *,
        key: str,
    ) -> str | None:
        """Return one decoded Redis string or a cache miss."""

        validated_key = _validate_key(
            key,
        )

        try:
            return await self._client.get(
                validated_key,
            )
        except RedisError as error:
            raise RedisUnavailableError("Redis GET failed.") from error

    async def set_text(
        self,
        *,
        key: str,
        value: str,
        ttl_seconds: int,
    ) -> None:
        """Store one string value with a required expiration."""

        validated_key = _validate_key(
            key,
        )

        if ttl_seconds < 1:
            raise ValueError("Redis ttl_seconds must be at least 1.")

        try:
            write_confirmed = await self._client.set(
                validated_key,
                value,
                ex=ttl_seconds,
            )
        except RedisError as error:
            raise RedisUnavailableError("Redis SET failed.") from error

        if write_confirmed is not True:
            raise RedisUnavailableError("Redis SET did not confirm the write.")

    async def set_if_absent(
        self,
        *,
        key: str,
        value: str,
        ttl_seconds: int,
    ) -> bool:
        """Atomically store a value only when the key does not exist."""

        validated_key = _validate_key(
            key,
        )

        if ttl_seconds < 1:
            raise ValueError("Redis ttl_seconds must be at least 1.")

        try:
            write_confirmed = await self._client.set(
                validated_key,
                value,
                ex=ttl_seconds,
                nx=True,
            )
        except RedisError as error:
            raise RedisUnavailableError("Redis SET NX failed.") from error

        return write_confirmed is True

    async def delete_if_value(
        self,
        *,
        key: str,
        expected_value: str,
    ) -> bool:
        """Atomically delete a key only when its value matches."""

        validated_key = _validate_key(
            key,
        )

        if not expected_value.strip():
            raise ValueError("Redis expected_value must not be empty.")

        try:
            raw_deleted_count = await self._client.eval(
                _COMPARE_AND_DELETE_SCRIPT,
                1,
                validated_key,
                expected_value,
            )
        except RedisError as error:
            raise RedisUnavailableError("Redis compare-and-delete failed.") from error

        if not isinstance(
            raw_deleted_count,
            int,
        ):
            raise RedisUnavailableError("Redis compare-and-delete returned an invalid response.")

        return raw_deleted_count > 0

    async def increment_with_ttl(
        self,
        *,
        key: str,
        ttl_seconds: int,
    ) -> tuple[int, int]:
        """Atomically increment a counter and initialize its expiration."""

        validated_key = _validate_key(
            key,
        )

        if ttl_seconds < 1:
            raise ValueError("Redis ttl_seconds must be at least 1.")

        try:
            raw_result = await self._client.eval(
                _INCREMENT_WITH_TTL_SCRIPT,
                1,
                validated_key,
                str(ttl_seconds),
            )
        except RedisError as error:
            raise RedisUnavailableError("Redis rate-limit increment failed.") from error

        if (
            not isinstance(
                raw_result,
                (list, tuple),
            )
            or len(raw_result) != 2
        ):
            raise RedisUnavailableError("Redis rate-limit increment returned an invalid response.")

        request_count, remaining_ttl = raw_result

        if (
            not isinstance(request_count, int)
            or isinstance(request_count, bool)
            or not isinstance(remaining_ttl, int)
            or isinstance(remaining_ttl, bool)
            or request_count < 1
            or remaining_ttl < 0
        ):
            raise RedisUnavailableError(
                "Redis rate-limit increment returned invalid counter values."
            )

        return (
            request_count,
            remaining_ttl,
        )

    async def delete(
        self,
        *,
        key: str,
    ) -> bool:
        """Delete one key and return whether it existed."""

        validated_key = _validate_key(
            key,
        )

        try:
            deleted_count = await self._client.delete(
                validated_key,
            )
        except RedisError as error:
            raise RedisUnavailableError("Redis DELETE failed.") from error

        return deleted_count > 0

    async def ttl_seconds(
        self,
        *,
        key: str,
    ) -> int:
        """Return Redis TTL semantics for one key."""

        validated_key = _validate_key(
            key,
        )

        try:
            return await self._client.ttl(
                validated_key,
            )
        except RedisError as error:
            raise RedisUnavailableError("Redis TTL failed.") from error

    async def close(self) -> None:
        """Close the Redis client and its owned connection pool."""

        await self._client.aclose()
