import asyncio
from typing import cast

import pytest

from app.services.vector_store.milvus import (
    MilvusVectorStore,
)


class FakeAsyncMilvusClient:
    """Record collection-management operations."""

    def __init__(
        self,
        *,
        collection_exists: bool,
    ) -> None:
        self.collection_exists = collection_exists
        self.has_collection_calls: list[str] = []
        self.load_collection_calls: list[str] = []
        self.create_collection_calls = 0
        self.created_collection_name: str | None = None
        self.created_schema: object | None = None
        self.created_index_params: object | None = None
        self.created_consistency_level: str | None = None
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
        self.created_collection_name = collection_name
        self.created_schema = schema
        self.created_index_params = index_params
        self.created_consistency_level = consistency_level
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

    async def close(self) -> None:
        self.closed = True


def test_initialize_creates_expected_collection_schema() -> None:
    client = FakeAsyncMilvusClient(
        collection_exists=False,
    )
    store = MilvusVectorStore(
        dimensions=1024,
        collection_name="private_document_chunks_test",
        uri="http://milvus.test:19530",
        client=client,
    )

    asyncio.run(store.initialize())

    assert store.dimensions == 1024
    assert store.collection_name == "private_document_chunks_test"
    assert client.has_collection_calls == ["private_document_chunks_test"]
    assert client.create_collection_calls == 1
    assert client.created_collection_name == "private_document_chunks_test"
    assert client.created_consistency_level == "Strong"
    assert client.load_collection_calls == ["private_document_chunks_test"]

    schema_to_dict = getattr(
        client.created_schema,
        "to_dict",
        None,
    )
    assert callable(schema_to_dict)

    schema_data = cast(
        dict[str, object],
        schema_to_dict(),
    )
    fields = cast(
        list[dict[str, object]],
        schema_data["fields"],
    )
    fields_by_name = {cast(str, field["name"]): field for field in fields}

    assert set(fields_by_name) == {
        "chunk_id",
        "document_id",
        "tenant_id",
        "filename",
        "media_type",
        "position",
        "word_start",
        "word_end",
        "content",
        "embedding",
    }

    assert fields_by_name["chunk_id"]["is_primary"] is True

    embedding_params = cast(
        dict[str, object],
        fields_by_name["embedding"]["params"],
    )
    assert embedding_params["dim"] == 1024


def test_initialize_creates_cosine_index() -> None:
    client = FakeAsyncMilvusClient(
        collection_exists=False,
    )
    store = MilvusVectorStore(
        dimensions=1024,
        collection_name="private_chunks_test",
        uri="http://milvus.test:19530",
        client=client,
    )

    asyncio.run(store.initialize())

    index_params = cast(
        list[object],
        client.created_index_params,
    )
    index_data: list[dict[str, object]] = []

    for index_param in index_params:
        to_dict = getattr(
            index_param,
            "to_dict",
            None,
        )
        assert callable(to_dict)

        index_data.append(
            cast(
                dict[str, object],
                to_dict(),
            )
        )

    assert index_data == [
        {
            "field_name": "embedding",
            "index_type": "AUTOINDEX",
            "index_name": "",
            "metric_type": "COSINE",
        }
    ]


def test_initialize_uses_existing_collection() -> None:
    client = FakeAsyncMilvusClient(
        collection_exists=True,
    )
    store = MilvusVectorStore(
        dimensions=1024,
        collection_name="existing_collection",
        uri="http://milvus.test:19530",
        client=client,
    )

    asyncio.run(store.initialize())

    assert client.create_collection_calls == 0
    assert client.load_collection_calls == ["existing_collection"]


def test_initialize_is_idempotent() -> None:
    client = FakeAsyncMilvusClient(
        collection_exists=False,
    )
    store = MilvusVectorStore(
        dimensions=1024,
        collection_name="idempotent_collection",
        uri="http://milvus.test:19530",
        client=client,
    )

    async def initialize_twice() -> None:
        await store.initialize()
        await store.initialize()

    asyncio.run(initialize_twice())

    assert client.has_collection_calls == ["idempotent_collection"]
    assert client.create_collection_calls == 1
    assert client.load_collection_calls == ["idempotent_collection"]


def test_close_closes_underlying_client() -> None:
    client = FakeAsyncMilvusClient(
        collection_exists=True,
    )
    store = MilvusVectorStore(
        dimensions=1024,
        collection_name="close_collection",
        uri="http://milvus.test:19530",
        client=client,
    )

    asyncio.run(store.close())

    assert client.closed is True


@pytest.mark.parametrize(
    "dimensions",
    [
        0,
        1,
    ],
)
def test_store_rejects_invalid_dimensions(
    dimensions: int,
) -> None:
    client = FakeAsyncMilvusClient(
        collection_exists=True,
    )

    with pytest.raises(
        ValueError,
        match="Milvus dimensions must be at least 2",
    ):
        MilvusVectorStore(
            dimensions=dimensions,
            collection_name="valid_collection",
            uri="http://milvus.test:19530",
            client=client,
        )


@pytest.mark.parametrize(
    "collection_name",
    [
        "",
        "1invalid",
        "invalid-name",
    ],
)
def test_store_rejects_invalid_collection_name(
    collection_name: str,
) -> None:
    client = FakeAsyncMilvusClient(
        collection_exists=True,
    )

    with pytest.raises(
        ValueError,
        match="Invalid Milvus collection name",
    ):
        MilvusVectorStore(
            dimensions=1024,
            collection_name=collection_name,
            uri="http://milvus.test:19530",
            client=client,
        )
