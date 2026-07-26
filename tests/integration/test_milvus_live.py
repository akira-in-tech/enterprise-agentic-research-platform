from uuid import uuid4

import pytest
from pymilvus import AsyncMilvusClient  # type: ignore[import-untyped]

from app.core.config import settings
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


def create_test_chunk(
    *,
    tenant_id: str,
    filename: str,
    content: str,
) -> DocumentChunk:
    """Create one deterministic chunk for the live Milvus test."""

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


@pytest.mark.integration
@pytest.mark.anyio
async def test_milvus_live_vector_store_round_trip() -> None:
    """Verify real upsert, tenant search and document deletion."""

    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    collection_name = f"private_chunks_live_{uuid4().hex[:12]}"
    token = settings.milvus_token.get_secret_value().strip()

    raw_client = AsyncMilvusClient(
        uri=settings.milvus_uri,
        token=token,
    )
    store = MilvusVectorStore(
        dimensions=2,
        collection_name=collection_name,
        uri=settings.milvus_uri,
        token=token,
        client=raw_client,
    )

    tenant_a_postgres = create_test_chunk(
        tenant_id="tenant-a",
        filename="postgresql.md",
        content=("PostgreSQL B-tree indexes support ordered range queries."),
    )
    tenant_a_redis = create_test_chunk(
        tenant_id="tenant-a",
        filename="redis.md",
        content=("Redis append-only files provide durable persistence."),
    )
    tenant_b_private = create_test_chunk(
        tenant_id="tenant-b",
        filename="private-networking.md",
        content=("Private tenant networking and HTTP connection guidance."),
    )

    try:
        await store.upsert(
            [
                VectorRecord(
                    chunk=tenant_a_postgres,
                    embedding=(1.0, 0.0),
                ),
                VectorRecord(
                    chunk=tenant_a_redis,
                    embedding=(0.0, 1.0),
                ),
                VectorRecord(
                    chunk=tenant_b_private,
                    embedding=(1.0, 0.0),
                ),
            ]
        )

        tenant_a_matches = await store.search(
            tenant_id="tenant-a",
            query_vector=(1.0, 0.0),
            limit=5,
        )

        assert [match.chunk.chunk_id for match in tenant_a_matches] == [
            tenant_a_postgres.chunk_id,
            tenant_a_redis.chunk_id,
        ]
        assert all(match.chunk.tenant_id == "tenant-a" for match in tenant_a_matches)
        assert tenant_a_matches[0].score == pytest.approx(
            1.0,
            abs=1e-5,
        )
        assert tenant_a_matches[1].score == pytest.approx(
            0.0,
            abs=1e-5,
        )

        tenant_b_matches = await store.search(
            tenant_id="tenant-b",
            query_vector=(1.0, 0.0),
            limit=5,
        )

        assert [match.chunk.chunk_id for match in tenant_b_matches] == [tenant_b_private.chunk_id]
        assert tenant_b_matches[0].chunk.tenant_id == "tenant-b"

        deleted_count = await store.delete_document(
            tenant_id="tenant-a",
            document_id=tenant_a_postgres.document_id,
        )

        assert deleted_count == 1

        tenant_a_after_delete = await store.search(
            tenant_id="tenant-a",
            query_vector=(1.0, 0.0),
            limit=5,
        )

        assert [match.chunk.chunk_id for match in tenant_a_after_delete] == [
            tenant_a_redis.chunk_id
        ]

        tenant_b_after_delete = await store.search(
            tenant_id="tenant-b",
            query_vector=(1.0, 0.0),
            limit=5,
        )

        assert [match.chunk.chunk_id for match in tenant_b_after_delete] == [
            tenant_b_private.chunk_id
        ]
    finally:
        if await raw_client.has_collection(
            collection_name,
        ):
            await raw_client.drop_collection(
                collection_name,
            )

        await store.close()
