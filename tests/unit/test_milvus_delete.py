import asyncio

import pytest

from app.services.vector_store.base import VectorStore
from app.services.vector_store.milvus import (
    MilvusVectorStore,
)


class FakeAsyncMilvusClient:
    """Record Milvus operations used by delete tests."""

    def __init__(
        self,
        *,
        delete_result: object,
    ) -> None:
        self.delete_result = delete_result
        self.has_collection_calls: list[str] = []
        self.load_collection_calls: list[str] = []
        self.delete_calls: list[
            tuple[
                str,
                str,
            ]
        ] = []
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
        return [[]]

    async def delete(
        self,
        collection_name: str,
        *,
        filter: str,
    ) -> object:
        self.delete_calls.append(
            (
                collection_name,
                filter,
            )
        )
        return self.delete_result

    async def close(self) -> None:
        self.closed = True


def test_delete_document_uses_tenant_and_document_filter() -> None:
    client = FakeAsyncMilvusClient(
        delete_result={
            "delete_count": 2,
        },
    )
    store: VectorStore = MilvusVectorStore(
        dimensions=2,
        collection_name="private_chunks_test",
        uri="http://milvus.test:19530",
        client=client,
    )

    deleted_count = asyncio.run(
        store.delete_document(
            tenant_id="tenant-acme",
            document_id="DOC-0123456789ABCDEF",
        )
    )

    assert deleted_count == 2
    assert client.has_collection_calls == ["private_chunks_test"]
    assert client.load_collection_calls == ["private_chunks_test"]
    assert client.delete_calls == [
        (
            "private_chunks_test",
            ('tenant_id == "tenant-acme" and document_id == "DOC-0123456789ABCDEF"'),
        )
    ]


def test_delete_document_returns_zero_when_nothing_matches() -> None:
    client = FakeAsyncMilvusClient(
        delete_result={
            "delete_count": 0,
        },
    )
    store = MilvusVectorStore(
        dimensions=2,
        collection_name="private_chunks_test",
        uri="http://milvus.test:19530",
        client=client,
    )

    deleted_count = asyncio.run(
        store.delete_document(
            tenant_id="tenant-acme",
            document_id="DOC-0123456789ABCDEF",
        )
    )

    assert deleted_count == 0


def test_delete_document_escapes_filter_values() -> None:
    client = FakeAsyncMilvusClient(
        delete_result={
            "delete_count": 1,
        },
    )
    store = MilvusVectorStore(
        dimensions=2,
        collection_name="private_chunks_test",
        uri="http://milvus.test:19530",
        client=client,
    )

    asyncio.run(
        store.delete_document(
            tenant_id='tenant-"blue"\\team',
            document_id="DOC-0123456789ABCDEF",
        )
    )

    assert client.delete_calls == [
        (
            "private_chunks_test",
            ('tenant_id == "tenant-\\"blue\\"\\\\team" and document_id == "DOC-0123456789ABCDEF"'),
        )
    ]


@pytest.mark.parametrize(
    ("tenant_id", "document_id", "expected_error"),
    [
        (
            "   ",
            "DOC-0123456789ABCDEF",
            "tenant_id must not be empty",
        ),
        (
            "tenant-acme",
            "   ",
            "document_id must not be empty",
        ),
    ],
)
def test_delete_document_rejects_empty_identifiers(
    tenant_id: str,
    document_id: str,
    expected_error: str,
) -> None:
    client = FakeAsyncMilvusClient(
        delete_result={
            "delete_count": 1,
        },
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
            store.delete_document(
                tenant_id=tenant_id,
                document_id=document_id,
            )
        )

    assert client.has_collection_calls == []
    assert client.delete_calls == []


@pytest.mark.parametrize(
    ("delete_result", "expected_error"),
    [
        (
            None,
            "invalid response",
        ),
        (
            {},
            "invalid delete count",
        ),
        (
            {
                "delete_count": True,
            },
            "invalid delete count",
        ),
        (
            {
                "delete_count": -1,
            },
            "invalid delete count",
        ),
    ],
)
def test_delete_document_rejects_invalid_response(
    delete_result: object,
    expected_error: str,
) -> None:
    client = FakeAsyncMilvusClient(
        delete_result=delete_result,
    )
    store = MilvusVectorStore(
        dimensions=2,
        collection_name="private_chunks_test",
        uri="http://milvus.test:19530",
        client=client,
    )

    with pytest.raises(
        RuntimeError,
        match=expected_error,
    ):
        asyncio.run(
            store.delete_document(
                tenant_id="tenant-acme",
                document_id="DOC-0123456789ABCDEF",
            )
        )
