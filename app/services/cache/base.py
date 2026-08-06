from typing import Protocol


class TextCacheClient(Protocol):
    """Text operations shared by Redis-backed cache services."""

    async def get_text(
        self,
        *,
        key: str,
    ) -> str | None:
        """Return one cached text value."""

    async def set_text(
        self,
        *,
        key: str,
        value: str,
        ttl_seconds: int,
    ) -> None:
        """Store one text value with expiration."""

    async def delete(
        self,
        *,
        key: str,
    ) -> bool:
        """Delete one cached value."""


class AtomicLockClient(Protocol):
    """Atomic operations required by distributed lock services."""

    async def set_if_absent(
        self,
        *,
        key: str,
        value: str,
        ttl_seconds: int,
    ) -> bool:
        """Atomically create one expiring lock value."""

    async def delete_if_value(
        self,
        *,
        key: str,
        expected_value: str,
    ) -> bool:
        """Atomically delete a lock owned by the expected value."""

    async def extend_if_value(
        self,
        *,
        key: str,
        expected_value: str,
        ttl_seconds: int,
    ) -> bool:
        """Atomically extend a lock's TTL only when still owned by the expected value."""


class RateLimitCounterClient(Protocol):
    """Atomic counter operation required by rate-limit services."""

    async def increment_with_ttl(
        self,
        *,
        key: str,
        ttl_seconds: int,
    ) -> tuple[int, int]:
        """Increment a counter and return its value and remaining TTL."""


class CacheUnavailableError(RuntimeError):
    """Represent an unavailable optional cache provider."""
