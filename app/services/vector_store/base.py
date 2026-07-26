from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.schemas.document import DocumentChunk

type Vector = tuple[float, ...]


@dataclass(frozen=True, slots=True)
class VectorRecord:
    """Represent one chunk and its embedding."""

    chunk: DocumentChunk
    embedding: Vector


@dataclass(frozen=True, slots=True)
class VectorSearchResult:
    """Represent one vector similarity match."""

    chunk: DocumentChunk
    score: float


class VectorStore(Protocol):
    """Define provider-neutral vector storage behavior."""

    @property
    def dimensions(self) -> int:
        """Return the required vector dimensions."""
        ...

    async def upsert(
        self,
        records: Sequence[VectorRecord],
    ) -> None:
        """Insert or replace vector records."""
        ...

    async def search(
        self,
        *,
        tenant_id: str,
        query_vector: Sequence[float],
        limit: int = 5,
    ) -> list[VectorSearchResult]:
        """Search vectors belonging to one tenant."""
        ...

    async def delete_document(
        self,
        *,
        tenant_id: str,
        document_id: str,
    ) -> int:
        """Delete one tenant's records for a document."""
        ...
