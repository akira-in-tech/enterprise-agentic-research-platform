import asyncio
import json
import math
import re
from collections.abc import Sequence
from typing import Protocol, cast

from pymilvus import (  # type: ignore[import-untyped]
    AsyncMilvusClient,
    DataType,
)
from pymilvus.exceptions import (  # type: ignore[import-untyped]
    ConnectError,
    MilvusUnavailableException,
)

from app.core.circuit_breaker import CircuitBreaker
from app.core.config import settings
from app.core.retry import call_with_backoff
from app.schemas.document import DocumentChunk
from app.services.vector_store.base import (
    Vector,
    VectorRecord,
    VectorSearchResult,
)

# Retry only connectivity-level failures. Other MilvusException subtypes
# (bad params, missing collection, schema mismatch) indicate a bug in this
# client's own request, not a transient condition -- retrying would just
# delay the same failure.
DEFAULT_RETRYABLE_ERRORS: tuple[type[Exception], ...] = (
    MilvusUnavailableException,
    ConnectError,
)

COLLECTION_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,254}$")


class AsyncMilvusClientProtocol(Protocol):
    """Describe Milvus operations used by this adapter."""

    async def has_collection(
        self,
        collection_name: str,
    ) -> bool: ...

    async def create_collection(
        self,
        collection_name: str,
        *,
        schema: object,
        index_params: object,
        consistency_level: str,
    ) -> None: ...

    async def load_collection(
        self,
        collection_name: str,
    ) -> None: ...

    async def upsert(
        self,
        collection_name: str,
        *,
        data: list[dict[str, object]],
    ) -> object: ...

    async def search(
        self,
        collection_name: str,
        *,
        data: list[list[float]],
        filter: str,
        limit: int,
        output_fields: list[str],
        search_params: dict[str, object],
        anns_field: str,
    ) -> list[list[dict[str, object]]]: ...

    async def delete(
        self,
        collection_name: str,
        *,
        filter: str,
    ) -> object: ...

    async def close(self) -> None: ...


class MilvusVectorStore:
    """Manage the Milvus private-document collection."""

    def __init__(
        self,
        *,
        dimensions: int | None = None,
        collection_name: str | None = None,
        uri: str | None = None,
        token: str | None = None,
        client: AsyncMilvusClientProtocol | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        retryable_errors: tuple[type[Exception], ...] = DEFAULT_RETRYABLE_ERRORS,
    ) -> None:
        selected_dimensions = (
            dimensions if dimensions is not None else settings.ollama_embedding_dimensions
        )
        selected_collection = (
            collection_name if collection_name is not None else settings.milvus_collection
        ).strip()
        selected_uri = (uri if uri is not None else settings.milvus_uri).strip()
        selected_token = (
            token if token is not None else settings.milvus_token.get_secret_value()
        ).strip()

        if selected_dimensions < 2:
            raise ValueError("Milvus dimensions must be at least 2.")

        if not COLLECTION_NAME_PATTERN.fullmatch(selected_collection):
            raise ValueError("Invalid Milvus collection name.")

        if not selected_uri:
            raise ValueError("Milvus URI must not be empty.")

        self._dimensions = selected_dimensions
        self._collection_name = selected_collection
        self._initialized = False
        self._initialize_lock = asyncio.Lock()
        self._circuit_breaker = circuit_breaker
        self._retryable_errors = retryable_errors

        if client is None:
            raw_client = AsyncMilvusClient(
                uri=selected_uri,
                token=selected_token,
            )
            self._client = cast(
                AsyncMilvusClientProtocol,
                raw_client,
            )
        else:
            self._client = client

    @property
    def dimensions(self) -> int:
        """Return the collection vector dimensions."""

        return self._dimensions

    @property
    def collection_name(self) -> str:
        """Return the configured collection name."""

        return self._collection_name

    async def initialize(self) -> None:
        """Create and load the collection once."""

        if self._initialized:
            return

        async with self._initialize_lock:
            if self._initialized:
                return

            exists = await self._client.has_collection(self._collection_name)

            if not exists:
                schema = self._build_schema()
                index_params = self._build_index_params()

                await self._client.create_collection(
                    self._collection_name,
                    schema=schema,
                    index_params=index_params,
                    consistency_level="Strong",
                )

            await self._client.load_collection(self._collection_name)
            self._initialized = True

    async def upsert(
        self,
        records: Sequence[VectorRecord],
    ) -> None:
        """Validate and upsert private-document vectors."""

        rows = [self._build_row(record) for record in records]

        if not rows:
            return

        await self.initialize()

        await self._client.upsert(
            self._collection_name,
            data=rows,
        )

    async def search(
        self,
        *,
        tenant_id: str,
        query_vector: Sequence[float],
        limit: int = 5,
        document_ids: Sequence[str] | None = None,
    ) -> list[VectorSearchResult]:
        """Search private-document vectors for one tenant."""

        normalized_tenant_id = tenant_id.strip()

        if not normalized_tenant_id:
            raise ValueError("tenant_id must not be empty.")

        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100.")

        validated_query = self._validate_vector(
            query_vector,
            field_name="Query vector",
        )

        search_filter = f"tenant_id == {json.dumps(normalized_tenant_id, ensure_ascii=False)}"

        if document_ids is not None:
            normalized_document_ids = [document_id.strip() for document_id in document_ids]

            if not normalized_document_ids:
                return []

            document_ids_json = json.dumps(normalized_document_ids, ensure_ascii=False)
            search_filter += f" and document_id in {document_ids_json}"

        await self.initialize()

        async def run_search() -> list[list[dict[str, object]]]:
            return await self._client.search(
                self._collection_name,
                data=[list(validated_query)],
                filter=search_filter,
                limit=limit,
                output_fields=[
                    "document_id",
                    "tenant_id",
                    "filename",
                    "media_type",
                    "position",
                    "word_start",
                    "word_end",
                    "content",
                ],
                search_params={
                    "metric_type": "COSINE",
                    "params": {},
                },
                anns_field="embedding",
            )

        async def run_search_with_breaker() -> list[list[dict[str, object]]]:
            if self._circuit_breaker is not None:
                return await self._circuit_breaker.call(run_search)

            return await run_search()

        search_results = await call_with_backoff(
            run_search_with_breaker,
            retryable=self._retryable_errors,
        )

        if not search_results:
            return []

        return [self._build_search_result(hit) for hit in search_results[0]]

    async def delete_document(
        self,
        *,
        tenant_id: str,
        document_id: str,
    ) -> int:
        """Delete one tenant's vectors for one document."""

        normalized_tenant_id = tenant_id.strip()
        normalized_document_id = document_id.strip()

        if not normalized_tenant_id:
            raise ValueError("tenant_id must not be empty.")

        if not normalized_document_id:
            raise ValueError("document_id must not be empty.")

        await self.initialize()

        delete_result = await self._client.delete(
            self._collection_name,
            filter=(
                "tenant_id == "
                f"{json.dumps(normalized_tenant_id, ensure_ascii=False)} "
                "and document_id == "
                f"{json.dumps(normalized_document_id, ensure_ascii=False)}"
            ),
        )

        if not isinstance(delete_result, dict):
            raise RuntimeError("Milvus delete returned an invalid response.")

        deleted_count = delete_result.get("delete_count")

        if (
            isinstance(deleted_count, bool)
            or not isinstance(deleted_count, int)
            or deleted_count < 0
        ):
            raise RuntimeError("Milvus delete returned an invalid delete count.")

        return deleted_count

    async def close(self) -> None:
        """Close the underlying Milvus client."""

        await self._client.close()

    def _build_row(
        self,
        record: VectorRecord,
    ) -> dict[str, object]:
        """Convert one provider-neutral record into a Milvus row."""

        embedding = self._validate_vector(
            record.embedding,
            field_name="Embedding",
        )
        chunk = record.chunk

        return {
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "tenant_id": chunk.tenant_id,
            "filename": chunk.filename,
            "media_type": chunk.media_type,
            "position": chunk.position,
            "word_start": chunk.word_start,
            "word_end": chunk.word_end,
            "content": chunk.content,
            "embedding": list(embedding),
        }

    def _validate_vector(
        self,
        vector: Sequence[float],
        *,
        field_name: str,
    ) -> Vector:
        """Return one validated, normalized vector."""

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
    def _build_search_result(
        hit: dict[str, object],
    ) -> VectorSearchResult:
        """Convert one Milvus hit into a domain search result."""

        chunk_id = hit.get("chunk_id")

        if chunk_id is None:
            chunk_id = hit.get("id")

        if not isinstance(chunk_id, str):
            raise RuntimeError("Milvus search hit is missing a valid chunk ID.")

        entity = hit.get("entity")

        if not isinstance(entity, dict):
            raise RuntimeError("Milvus search hit is missing entity data.")

        chunk_data: dict[str, object] = dict(entity)
        chunk_data["chunk_id"] = chunk_id

        try:
            chunk = DocumentChunk.model_validate(chunk_data)
        except ValueError as error:
            raise RuntimeError("Milvus returned invalid document chunk data.") from error

        raw_score = hit.get("distance")

        if isinstance(raw_score, bool) or not isinstance(
            raw_score,
            (int, float),
        ):
            raise RuntimeError("Milvus search hit is missing a numeric score.")

        score = float(raw_score)

        if not math.isfinite(score):
            raise RuntimeError("Milvus search hit contains a non-finite score.")

        return VectorSearchResult(
            chunk=chunk,
            score=score,
        )

    def _build_schema(self) -> object:
        schema = AsyncMilvusClient.create_schema(
            auto_id=False,
            enable_dynamic_field=False,
        )

        schema.add_field(
            field_name="chunk_id",
            datatype=DataType.VARCHAR,
            is_primary=True,
            max_length=20,
        )
        schema.add_field(
            field_name="document_id",
            datatype=DataType.VARCHAR,
            max_length=20,
        )
        schema.add_field(
            field_name="tenant_id",
            datatype=DataType.VARCHAR,
            max_length=100,
        )
        schema.add_field(
            field_name="filename",
            datatype=DataType.VARCHAR,
            max_length=255,
        )
        schema.add_field(
            field_name="media_type",
            datatype=DataType.VARCHAR,
            max_length=50,
        )
        schema.add_field(
            field_name="position",
            datatype=DataType.INT64,
        )
        schema.add_field(
            field_name="word_start",
            datatype=DataType.INT64,
        )
        schema.add_field(
            field_name="word_end",
            datatype=DataType.INT64,
        )
        schema.add_field(
            field_name="content",
            datatype=DataType.VARCHAR,
            max_length=65_535,
        )
        schema.add_field(
            field_name="embedding",
            datatype=DataType.FLOAT_VECTOR,
            dim=self._dimensions,
        )

        return schema

    @staticmethod
    def _build_index_params() -> object:
        index_params = AsyncMilvusClient.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            index_type="AUTOINDEX",
            metric_type="COSINE",
        )

        return index_params
