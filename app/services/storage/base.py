from typing import Protocol


class DocumentStorage(Protocol):
    """Define durable source-document object operations."""

    async def put(self, *, key: str, content: bytes) -> None:
        """Store one immutable source object."""
        ...

    async def get(self, *, key: str) -> bytes:
        """Read one source object."""
        ...

    async def delete(self, *, key: str) -> None:
        """Delete one source object idempotently."""
        ...


class DocumentStorageError(RuntimeError):
    """Represent an unavailable or failed source-document store."""


class DocumentNotFoundError(DocumentStorageError):
    """Represent a read for a source-document key that does not exist."""
