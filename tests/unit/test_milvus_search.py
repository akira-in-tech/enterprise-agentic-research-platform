import asyncio

import pytest

from app.schemas.document import DocumentChunk
from app.services.knowledge.chunking import (
    chunk_document,
)
from app.services.knowledge.documents import (
    create_text_document,
)
from app.services.vector_store.milvus import (
    MilvusVectorStore,
)


class FakeAsyncMilvusClient:
    """Record Milvus operations used by search tests."""

    def __init__(
        self,
        *,
        search_results: list[list[dict[str, object]]],
    ) -> None:
        self.search_results = search_results
        self.has_collection_calls: list[str] = []
        self.load_collection_calls: list[str] = []
        self.search_calls: list[dict[str, object]] = []
        self.closed = False

    async def has_collection(
        self,
        collection_name: str,
    ) -> bool:
        self.has_collection_calls.append(collection_name)
        return True

    async def create_collection(
        self,
        collection_name: str,
        *,
        schema: object,
        index_params: object,
        consistency_level: str,
    ) -> None:
        raise AssertionError("Existing test collection must not be created.")

    async def load_collection(
        self,
        collection_name: str,
    ) -> None:
        self.load_collection_calls.append(collection_name)

    async def upsert(
        self,
        collection_name: str,
        *,
        data: list[dict[str, object]],
    ) -> object:
        return {
            "upsert_count": len(data),
        }

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
    ) -> list[list[dict[str, object]]]:
        self.search_calls.append(
            {
                "collection_name": collection_name,
                "data": data,
                "filter": filter,
                "limit": limit,
                "output_fields": output_fields,
                "search_params": search_params,
                "anns_field": anns_field,
            }
        )
        return self.search_results

    async def delete(
        self,
        collection_name: str,
        *,
        filter: str,
    ) -> object:
        return {
            "delete_count": 0,
        }

    async def close(self) -> None:
        self.closed = True


def create_test_chunk() -> DocumentChunk:
    """Create one deterministic private-document chunk."""

    document = create_text_document(
        tenant_id="tenant-acme",
        filename="networking.md",
        raw_content=(
            b"HTTP persistent connections reduce repeated connection establishment overhead."
        ),
    )

    return chunk_document(
        document,
        max_words=50,
        overlap_words=0,
    )[0]


def create_search_hit(
    chunk: DocumentChunk,
    *,
    score: object = 0.93,
) -> dict[str, object]:
    """Create one Milvus-style search hit."""

    entity = chunk.model_dump(
        exclude={
            "chunk_id",
        }
    )

    return {
        "chunk_id": chunk.chunk_id,
        "distance": score,
        "entity": entity,
    }


def test_search_uses_cosine_metric_and_tenant_filter() -> None:
    chunk = create_test_chunk()
    client = FakeAsyncMilvusClient(
        search_results=[
            [
                create_search_hit(
                    chunk,
                    score=0.93,
                )
            ]
        ],
    )
    store = MilvusVectorStore(
        dimensions=2,
        collection_name="private_chunks_test",
        uri="http://milvus.test:19530",
        client=client,
    )

    matches = asyncio.run(
        store.search(
            tenant_id="tenant-acme",
            query_vector=(1.0, 0.0),
            limit=3,
        )
    )

    assert client.has_collection_calls == ["private_chunks_test"]
    assert client.load_collection_calls == ["private_chunks_test"]
    assert client.search_calls == [
        {
            "collection_name": "private_chunks_test",
            "data": [[1.0, 0.0]],
            "filter": 'tenant_id == "tenant-acme"',
            "limit": 3,
            "output_fields": [
                "document_id",
                "tenant_id",
                "filename",
                "media_type",
                "position",
                "word_start",
                "word_end",
                "content",
            ],
            "search_params": {
                "metric_type": "COSINE",
                "params": {},
            },
            "anns_field": "embedding",
        }
    ]

    assert len(matches) == 1
    assert matches[0].chunk == chunk
    assert matches[0].score == pytest.approx(0.93)


def test_search_accepts_generic_id_key() -> None:
    chunk = create_test_chunk()
    hit = create_search_hit(
        chunk,
        score=0.91,
    )

    hit["id"] = hit.pop("chunk_id")

    client = FakeAsyncMilvusClient(
        search_results=[
            [
                hit,
            ]
        ],
    )
    store = MilvusVectorStore(
        dimensions=2,
        collection_name="private_chunks_test",
        uri="http://milvus.test:19530",
        client=client,
    )

    matches = asyncio.run(
        store.search(
            tenant_id="tenant-acme",
            query_vector=(1.0, 0.0),
        )
    )

    assert len(matches) == 1
    assert matches[0].chunk == chunk
    assert matches[0].score == pytest.approx(0.91)


def test_search_returns_empty_list_for_no_hits() -> None:
    client = FakeAsyncMilvusClient(
        search_results=[[]],
    )
    store = MilvusVectorStore(
        dimensions=2,
        collection_name="private_chunks_test",
        uri="http://milvus.test:19530",
        client=client,
    )

    matches = asyncio.run(
        store.search(
            tenant_id="tenant-acme",
            query_vector=(1.0, 0.0),
        )
    )

    assert matches == []


def test_search_rejects_empty_tenant_before_initializing() -> None:
    client = FakeAsyncMilvusClient(
        search_results=[[]],
    )
    store = MilvusVectorStore(
        dimensions=2,
        collection_name="private_chunks_test",
        uri="http://milvus.test:19530",
        client=client,
    )

    with pytest.raises(
        ValueError,
        match="tenant_id must not be empty",
    ):
        asyncio.run(
            store.search(
                tenant_id="   ",
                query_vector=(1.0, 0.0),
            )
        )

    assert client.has_collection_calls == []
    assert client.search_calls == []


@pytest.mark.parametrize(
    "limit",
    [
        0,
        101,
    ],
)
def test_search_rejects_invalid_limit(
    limit: int,
) -> None:
    client = FakeAsyncMilvusClient(
        search_results=[[]],
    )
    store = MilvusVectorStore(
        dimensions=2,
        collection_name="private_chunks_test",
        uri="http://milvus.test:19530",
        client=client,
    )

    with pytest.raises(
        ValueError,
        match="limit must be between 1 and 100",
    ):
        asyncio.run(
            store.search(
                tenant_id="tenant-acme",
                query_vector=(1.0, 0.0),
                limit=limit,
            )
        )

    assert client.search_calls == []


@pytest.mark.parametrize(
    ("query_vector", "expected_error"),
    [
        (
            (1.0,),
            "exactly 2 values",
        ),
        (
            (float("nan"), 1.0),
            "only finite values",
        ),
        (
            (0.0, 0.0),
            "must not be a zero vector",
        ),
    ],
)
def test_search_rejects_invalid_query_vector(
    query_vector: tuple[float, ...],
    expected_error: str,
) -> None:
    client = FakeAsyncMilvusClient(
        search_results=[[]],
    )
    store = MilvusVectorStore(
        dimensions=2,
        collection_name="private_chunks_test",
        uri="http://milvus.test:19530",
        client=client,
    )

    with pytest.raises(
        ValueError,
        match=expected_error,
    ):
        asyncio.run(
            store.search(
                tenant_id="tenant-acme",
                query_vector=query_vector,
            )
        )

    assert client.search_calls == []


def test_search_rejects_malformed_milvus_hit() -> None:
    client = FakeAsyncMilvusClient(
        search_results=[
            [
                {
                    "id": "CHK-0123456789ABCDEF",
                    "distance": 0.8,
                }
            ]
        ],
    )
    store = MilvusVectorStore(
        dimensions=2,
        collection_name="private_chunks_test",
        uri="http://milvus.test:19530",
        client=client,
    )

    with pytest.raises(
        RuntimeError,
        match="missing entity data",
    ):
        asyncio.run(
            store.search(
                tenant_id="tenant-acme",
                query_vector=(1.0, 0.0),
            )
        )
