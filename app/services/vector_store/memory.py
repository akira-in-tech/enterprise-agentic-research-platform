import math
from collections.abc import Sequence

from app.services.vector_store.base import (
    Vector,
    VectorRecord,
    VectorSearchResult,
)


class InMemoryVectorStore:
    """Provide deterministic vector storage for unit tests."""

    def __init__(
        self,
        *,
        dimensions: int,
    ) -> None:
        if dimensions < 1:
            raise ValueError("dimensions must be at least 1.")

        self._dimensions = dimensions
        self._records: dict[
            tuple[str, str],
            VectorRecord,
        ] = {}

    @property
    def dimensions(self) -> int:
        """Return the required vector dimensions."""

        return self._dimensions

    async def upsert(
        self,
        records: Sequence[VectorRecord],
    ) -> None:
        """Validate and atomically upsert vector records."""

        validated_records: list[VectorRecord] = []

        for record in records:
            embedding = self._validate_vector(
                record.embedding,
                field_name="Embedding",
            )
            validated_records.append(
                VectorRecord(
                    chunk=record.chunk,
                    embedding=embedding,
                )
            )

        for record in validated_records:
            key = (
                record.chunk.tenant_id,
                record.chunk.chunk_id,
            )
            self._records[key] = record

    async def search(
        self,
        *,
        tenant_id: str,
        query_vector: Sequence[float],
        limit: int = 5,
        document_ids: Sequence[str] | None = None,
    ) -> list[VectorSearchResult]:
        """Return deterministic cosine-similarity matches."""

        normalized_tenant_id = tenant_id.strip()

        if not normalized_tenant_id:
            raise ValueError("tenant_id must not be empty.")

        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100.")

        validated_query = self._validate_vector(
            query_vector,
            field_name="Query vector",
        )

        allowed_document_ids = (
            {document_id.strip() for document_id in document_ids}
            if document_ids is not None
            else None
        )

        matches = [
            VectorSearchResult(
                chunk=record.chunk,
                score=self._cosine_similarity(
                    validated_query,
                    record.embedding,
                ),
            )
            for record in self._records.values()
            if (record.chunk.tenant_id == normalized_tenant_id)
            and (allowed_document_ids is None or record.chunk.document_id in allowed_document_ids)
        ]

        return sorted(
            matches,
            key=lambda match: (
                -match.score,
                match.chunk.chunk_id,
            ),
        )[:limit]

    async def delete_document(
        self,
        *,
        tenant_id: str,
        document_id: str,
    ) -> int:
        """Delete only records matching both tenant and document."""

        normalized_tenant_id = tenant_id.strip()
        normalized_document_id = document_id.strip()

        if not normalized_tenant_id:
            raise ValueError("tenant_id must not be empty.")

        if not normalized_document_id:
            raise ValueError("document_id must not be empty.")

        keys_to_delete = [
            key
            for key, record in self._records.items()
            if (
                record.chunk.tenant_id == normalized_tenant_id
                and record.chunk.document_id == normalized_document_id
            )
        ]

        for key in keys_to_delete:
            del self._records[key]

        return len(keys_to_delete)

    async def close(self) -> None:
        """Close the in-memory store without external cleanup."""

    def _validate_vector(
        self,
        vector: Sequence[float],
        *,
        field_name: str,
    ) -> Vector:
        if len(vector) != self._dimensions:
            raise ValueError(f"{field_name} must contain exactly {self._dimensions} values.")

        if any(
            isinstance(value, bool)
            or not isinstance(
                value,
                (int, float),
            )
            for value in vector
        ):
            raise ValueError(f"{field_name} must contain numeric values.")

        normalized_vector = tuple(float(value) for value in vector)

        if any(not math.isfinite(value) for value in normalized_vector):
            raise ValueError(f"{field_name} must contain only finite values.")

        if not any(value != 0.0 for value in normalized_vector):
            raise ValueError(f"{field_name} must not be a zero vector.")

        return normalized_vector

    @staticmethod
    def _cosine_similarity(
        left: Vector,
        right: Vector,
    ) -> float:
        dot_product = math.fsum(
            left_value * right_value
            for left_value, right_value in zip(
                left,
                right,
                strict=True,
            )
        )
        left_magnitude = math.sqrt(math.fsum(value * value for value in left))
        right_magnitude = math.sqrt(math.fsum(value * value for value in right))

        return dot_product / (left_magnitude * right_magnitude)
