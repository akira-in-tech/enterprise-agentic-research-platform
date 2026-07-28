from collections.abc import Awaitable
from typing import Protocol, cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings


class AsyncRedisClient(Protocol):
    """Redis operations required by the application wrapper."""

    def ping(self) -> Awaitable[bool]:
        """Return whether Redis is reachable."""

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


class RedisUnavailableError(RuntimeError):
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

    async def close(self) -> None:
        """Close the Redis client and its owned connection pool."""

        await self._client.aclose()
