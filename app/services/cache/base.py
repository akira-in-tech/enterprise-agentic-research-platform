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


class CacheUnavailableError(RuntimeError):
    """Represent an unavailable optional cache provider."""
