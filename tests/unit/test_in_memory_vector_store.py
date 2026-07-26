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
    VectorStore,
)
from app.services.vector_store.memory import (
    InMemoryVectorStore,
)


def create_test_chunk(
    *,
    tenant_id: str,
    filename: str,
    content: str,
) -> DocumentChunk:
    document = create_text_document(
        tenant_id=tenant_id,
        filename=filename,
        raw_content=content.encode(),
    )

    return chunk_document(
        document,
        max_words=50,
        overlap_words=0,
    )[0]


def test_search_ranks_results_by_cosine_similarity() -> None:
    store: VectorStore = InMemoryVectorStore(
        dimensions=2,
    )
    postgres_chunk = create_test_chunk(
        tenant_id="tenant-hennge",
        filename="postgresql.md",
        content="PostgreSQL B-tree indexing strategies.",
    )
    redis_chunk = create_test_chunk(
        tenant_id="tenant-hennge",
        filename="redis.md",
        content="Redis append-only file persistence.",
    )

    asyncio.run(
        store.upsert(
            [
                VectorRecord(
                    chunk=postgres_chunk,
                    embedding=(1.0, 0.0),
                ),
                VectorRecord(
                    chunk=redis_chunk,
                    embedding=(0.0, 1.0),
                ),
            ]
        )
    )

    matches = asyncio.run(
        store.search(
            tenant_id="tenant-hennge",
            query_vector=(1.0, 0.0),
            limit=2,
        )
    )

    assert store.dimensions == 2
    assert [match.chunk.chunk_id for match in matches] == [
        postgres_chunk.chunk_id,
        redis_chunk.chunk_id,
    ]
    assert matches[0].score == pytest.approx(1.0)
    assert matches[1].score == pytest.approx(0.0)


def test_search_enforces_tenant_isolation() -> None:
    store = InMemoryVectorStore(
        dimensions=2,
    )
    tenant_a_chunk = create_test_chunk(
        tenant_id="tenant-a",
        filename="networking.md",
        content="HTTP connection reuse.",
    )
    tenant_b_chunk = create_test_chunk(
        tenant_id="tenant-b",
        filename="networking.md",
        content="Private tenant networking notes.",
    )

    asyncio.run(
        store.upsert(
            [
                VectorRecord(
                    chunk=tenant_a_chunk,
                    embedding=(1.0, 0.0),
                ),
                VectorRecord(
                    chunk=tenant_b_chunk,
                    embedding=(1.0, 0.0),
                ),
            ]
        )
    )

    matches = asyncio.run(
        store.search(
            tenant_id="tenant-a",
            query_vector=(1.0, 0.0),
        )
    )

    assert [match.chunk.tenant_id for match in matches] == ["tenant-a"]
    assert matches[0].chunk.chunk_id == (tenant_a_chunk.chunk_id)


def test_upsert_replaces_existing_record() -> None:
    store = InMemoryVectorStore(
        dimensions=2,
    )
    chunk = create_test_chunk(
        tenant_id="tenant-hennge",
        filename="linux.md",
        content="Linux epoll readiness notification.",
    )

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
    asyncio.run(
        store.upsert(
            [
                VectorRecord(
                    chunk=chunk,
                    embedding=(0.0, 1.0),
                )
            ]
        )
    )

    matches = asyncio.run(
        store.search(
            tenant_id="tenant-hennge",
            query_vector=(0.0, 1.0),
        )
    )

    assert len(matches) == 1
    assert matches[0].score == pytest.approx(1.0)


def test_upsert_validates_batch_before_mutation() -> None:
    store = InMemoryVectorStore(
        dimensions=2,
    )
    valid_chunk = create_test_chunk(
        tenant_id="tenant-hennge",
        filename="valid.md",
        content="Valid distributed systems notes.",
    )
    invalid_chunk = create_test_chunk(
        tenant_id="tenant-hennge",
        filename="invalid.md",
        content="Invalid vector dimensions.",
    )

    with pytest.raises(
        ValueError,
        match="exactly 2 values",
    ):
        asyncio.run(
            store.upsert(
                [
                    VectorRecord(
                        chunk=valid_chunk,
                        embedding=(1.0, 0.0),
                    ),
                    VectorRecord(
                        chunk=invalid_chunk,
                        embedding=(1.0,),
                    ),
                ]
            )
        )

    matches = asyncio.run(
        store.search(
            tenant_id="tenant-hennge",
            query_vector=(1.0, 0.0),
        )
    )

    assert matches == []


def test_delete_document_preserves_other_records() -> None:
    store = InMemoryVectorStore(
        dimensions=2,
    )
    deleted_chunk = create_test_chunk(
        tenant_id="tenant-a",
        filename="delete.md",
        content="Document that will be deleted.",
    )
    preserved_chunk = create_test_chunk(
        tenant_id="tenant-a",
        filename="preserve.md",
        content="Document that must remain.",
    )
    other_tenant_chunk = create_test_chunk(
        tenant_id="tenant-b",
        filename="delete.md",
        content="Other tenant document.",
    )

    asyncio.run(
        store.upsert(
            [
                VectorRecord(
                    chunk=deleted_chunk,
                    embedding=(1.0, 0.0),
                ),
                VectorRecord(
                    chunk=preserved_chunk,
                    embedding=(0.0, 1.0),
                ),
                VectorRecord(
                    chunk=other_tenant_chunk,
                    embedding=(1.0, 0.0),
                ),
            ]
        )
    )

    deleted_count = asyncio.run(
        store.delete_document(
            tenant_id="tenant-a",
            document_id=deleted_chunk.document_id,
        )
    )

    tenant_a_matches = asyncio.run(
        store.search(
            tenant_id="tenant-a",
            query_vector=(1.0, 0.0),
        )
    )
    tenant_b_matches = asyncio.run(
        store.search(
            tenant_id="tenant-b",
            query_vector=(1.0, 0.0),
        )
    )

    assert deleted_count == 1
    assert [match.chunk.chunk_id for match in tenant_a_matches] == [preserved_chunk.chunk_id]
    assert [match.chunk.chunk_id for match in tenant_b_matches] == [other_tenant_chunk.chunk_id]


def test_empty_store_returns_no_matches() -> None:
    store = InMemoryVectorStore(
        dimensions=2,
    )

    matches = asyncio.run(
        store.search(
            tenant_id="tenant-hennge",
            query_vector=(1.0, 0.0),
        )
    )

    assert matches == []


@pytest.mark.parametrize(
    "dimensions",
    [
        0,
        -1,
    ],
)
def test_store_rejects_invalid_dimensions(
    dimensions: int,
) -> None:
    with pytest.raises(
        ValueError,
        match="dimensions must be at least 1",
    ):
        InMemoryVectorStore(
            dimensions=dimensions,
        )


@pytest.mark.parametrize(
    ("embedding", "expected_error"),
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
def test_upsert_rejects_invalid_embedding(
    embedding: tuple[float, ...],
    expected_error: str,
) -> None:
    store = InMemoryVectorStore(
        dimensions=2,
    )
    chunk = create_test_chunk(
        tenant_id="tenant-hennge",
        filename="invalid-vector.md",
        content="Invalid vector validation.",
    )

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


@pytest.mark.parametrize(
    ("query_vector", "expected_error"),
    [
        (
            (1.0,),
            "exactly 2 values",
        ),
        (
            (float("inf"), 1.0),
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
    store = InMemoryVectorStore(
        dimensions=2,
    )

    with pytest.raises(
        ValueError,
        match=expected_error,
    ):
        asyncio.run(
            store.search(
                tenant_id="tenant-hennge",
                query_vector=query_vector,
            )
        )


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
    store = InMemoryVectorStore(
        dimensions=2,
    )

    with pytest.raises(
        ValueError,
        match="limit must be between 1 and 100",
    ):
        asyncio.run(
            store.search(
                tenant_id="tenant-hennge",
                query_vector=(1.0, 0.0),
                limit=limit,
            )
        )
