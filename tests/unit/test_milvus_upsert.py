import asyncio

import pytest

from app.schemas.document import DocumentChunk
from app.services.knowledge.chunking import (
    chunk_document,
)
from app.services.knowledge.documents import (
    create_text_document,
)
from app.services.vector_store.base import (
    VectorRecord,
)
from app.services.vector_store.milvus import (
    MilvusVectorStore,
)


class FakeAsyncMilvusClient:
    """Record Milvus operations used by upsert tests."""

    def __init__(
        self,
        *,
        collection_exists: bool,
    ) -> None:
        self.collection_exists = collection_exists
        self.has_collection_calls: list[str] = []
        self.load_collection_calls: list[str] = []
        self.create_collection_calls = 0
        self.upsert_calls: list[
            tuple[
                str,
                list[dict[str, object]],
            ]
        ] = []
        self.closed = False

    async def has_collection(
        self,
        collection_name: str,
    ) -> bool:
        self.has_collection_calls.append(collection_name)
        return self.collection_exists

    async def create_collection(
        self,
        collection_name: str,
        *,
        schema: object,
        index_params: object,
        consistency_level: str,
    ) -> None:
        self.create_collection_calls += 1
        self.collection_exists = True

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
        self.upsert_calls.append(
            (
                collection_name,
                data,
            )
        )
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
        return [[]]

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


def create_test_chunks() -> list[DocumentChunk]:
    """Create two deterministic private-document chunks."""

    document = create_text_document(
        tenant_id="tenant-hennge",
        filename="postgresql.md",
        raw_content=(b"PostgreSQL B-tree indexes support ordered range queries efficiently."),
    )

    return chunk_document(
        document,
        max_words=4,
        overlap_words=0,
    )


def test_upsert_maps_vector_records_to_milvus_rows() -> None:
    client = FakeAsyncMilvusClient(
        collection_exists=True,
    )
    store = MilvusVectorStore(
        dimensions=2,
        collection_name="private_chunks_test",
        uri="http://milvus.test:19530",
        client=client,
    )
    chunks = create_test_chunks()

    asyncio.run(
        store.upsert(
            [
                VectorRecord(
                    chunk=chunks[0],
                    embedding=(1.0, 0.0),
                ),
                VectorRecord(
                    chunk=chunks[1],
                    embedding=(0.0, 1.0),
                ),
            ]
        )
    )

    assert client.has_collection_calls == ["private_chunks_test"]
    assert client.load_collection_calls == ["private_chunks_test"]
    assert len(client.upsert_calls) == 1

    collection_name, rows = client.upsert_calls[0]

    assert collection_name == "private_chunks_test"
    assert rows == [
        {
            "chunk_id": chunks[0].chunk_id,
            "document_id": chunks[0].document_id,
            "tenant_id": chunks[0].tenant_id,
            "filename": chunks[0].filename,
            "media_type": chunks[0].media_type,
            "position": chunks[0].position,
            "word_start": chunks[0].word_start,
            "word_end": chunks[0].word_end,
            "content": chunks[0].content,
            "embedding": [1.0, 0.0],
        },
        {
            "chunk_id": chunks[1].chunk_id,
            "document_id": chunks[1].document_id,
            "tenant_id": chunks[1].tenant_id,
            "filename": chunks[1].filename,
            "media_type": chunks[1].media_type,
            "position": chunks[1].position,
            "word_start": chunks[1].word_start,
            "word_end": chunks[1].word_end,
            "content": chunks[1].content,
            "embedding": [0.0, 1.0],
        },
    ]


def test_upsert_creates_missing_collection() -> None:
    client = FakeAsyncMilvusClient(
        collection_exists=False,
    )
    store = MilvusVectorStore(
        dimensions=2,
        collection_name="private_chunks_test",
        uri="http://milvus.test:19530",
        client=client,
    )
    chunk = create_test_chunks()[0]

    asyncio.run(
        store.upsert(
            [
                VectorRecord(
                    chunk=chunk,
                    embedding=(1.0, 0.0),
                )
            ]
        )
    )

    assert client.create_collection_calls == 1
    assert client.load_collection_calls == ["private_chunks_test"]
    assert len(client.upsert_calls) == 1


def test_empty_upsert_is_a_no_op() -> None:
    client = FakeAsyncMilvusClient(
        collection_exists=False,
    )
    store = MilvusVectorStore(
        dimensions=2,
        collection_name="private_chunks_test",
        uri="http://milvus.test:19530",
        client=client,
    )

    asyncio.run(store.upsert([]))

    assert client.has_collection_calls == []
    assert client.create_collection_calls == 0
    assert client.load_collection_calls == []
    assert client.upsert_calls == []


def test_upsert_validates_entire_batch_before_initializing() -> None:
    client = FakeAsyncMilvusClient(
        collection_exists=False,
    )
    store = MilvusVectorStore(
        dimensions=2,
        collection_name="private_chunks_test",
        uri="http://milvus.test:19530",
        client=client,
    )
    chunks = create_test_chunks()

    with pytest.raises(
        ValueError,
        match="exactly 2 values",
    ):
        asyncio.run(
            store.upsert(
                [
                    VectorRecord(
                        chunk=chunks[0],
                        embedding=(1.0, 0.0),
                    ),
                    VectorRecord(
                        chunk=chunks[1],
                        embedding=(1.0,),
                    ),
                ]
            )
        )

    assert client.has_collection_calls == []
    assert client.create_collection_calls == 0
    assert client.load_collection_calls == []
    assert client.upsert_calls == []


@pytest.mark.parametrize(
    ("embedding", "expected_error"),
    [
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
def test_upsert_rejects_invalid_embedding(
    embedding: tuple[float, ...],
    expected_error: str,
) -> None:
    client = FakeAsyncMilvusClient(
        collection_exists=True,
    )
    store = MilvusVectorStore(
        dimensions=2,
        collection_name="private_chunks_test",
        uri="http://milvus.test:19530",
        client=client,
    )
    chunk = create_test_chunks()[0]

    with pytest.raises(
        ValueError,
        match=expected_error,
    ):
        asyncio.run(
            store.upsert(
                [
                    VectorRecord(
                        chunk=chunk,
                        embedding=embedding,
                    )
                ]
            )
        )

    assert client.upsert_calls == []
