from uuid import uuid4

import pytest
from pymilvus import AsyncMilvusClient  # type: ignore[import-untyped]

from app.core.config import settings
from app.services.embeddings.ollama import (
    OllamaEmbeddingClient,
)
from app.services.knowledge.documents import (
    create_text_document,
)
from app.services.knowledge.indexing import (
    KnowledgeIndexer,
)
from app.services.knowledge.retrieval import (
    PrivateKnowledgeRetriever,
)
from app.services.vector_store.factory import (
    create_vector_store,
)
from app.services.vector_store.milvus import (
    MilvusVectorStore,
)


@pytest.mark.integration
@pytest.mark.anyio
async def test_private_rag_live_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Index and retrieve private documents using Ollama and Milvus."""

    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    collection_name = f"private_rag_live_{uuid4().hex[:12]}"
    token = settings.milvus_token.get_secret_value().strip()

    monkeypatch.setattr(
        settings,
        "milvus_collection",
        collection_name,
    )

    embedding_client = OllamaEmbeddingClient()
    vector_store = create_vector_store(
        "milvus",
        dimensions=embedding_client.dimensions,
    )

    assert isinstance(
        vector_store,
        MilvusVectorStore,
    )

    cleanup_client = AsyncMilvusClient(
        uri=settings.milvus_uri,
        token=token,
    )

    tenant_a_http = create_text_document(
        tenant_id="tenant-a",
        filename="http2.md",
        raw_content=(
            b"HTTP/2 multiplexes multiple streams over one "
            b"TCP connection. HPACK compresses HTTP headers."
        ),
    )
    tenant_a_redis = create_text_document(
        tenant_id="tenant-a",
        filename="redis.md",
        raw_content=(
            b"Redis append-only files record write operations "
            b"and support durable recovery after a restart."
        ),
    )
    tenant_b_http = create_text_document(
        tenant_id="tenant-b",
        filename="private-http2.md",
        raw_content=(
            b"HTTP/2 multiplexes multiple streams over one "
            b"TCP connection. This document belongs to tenant B."
        ),
    )

    indexer = KnowledgeIndexer(
        embedding_client,
        vector_store,
        max_words=50,
        overlap_words=0,
        embedding_batch_size=2,
    )
    retriever = PrivateKnowledgeRetriever(
        embedding_client,
        vector_store,
    )

    try:
        tenant_a_http_result = await indexer.index_document(tenant_a_http)
        tenant_a_redis_result = await indexer.index_document(tenant_a_redis)
        tenant_b_http_result = await indexer.index_document(tenant_b_http)

        assert tenant_a_http_result.chunk_count == 1
        assert tenant_a_redis_result.chunk_count == 1
        assert tenant_b_http_result.chunk_count == 1

        tenant_a_sources = await retriever.retrieve(
            query=tenant_a_http.content,
            tenant_id="tenant-a",
            limit=5,
        )

        assert tenant_a_sources
        assert tenant_a_sources[0].document_id == (tenant_a_http.document_id)
        assert {source.document_id for source in tenant_a_sources} == {
            tenant_a_http.document_id,
            tenant_a_redis.document_id,
        }
        assert all(source.source_id.startswith("PRIVATE-") for source in tenant_a_sources)
        assert all(source.provider == "private_knowledge" for source in tenant_a_sources)
        assert tenant_b_http.document_id not in {source.document_id for source in tenant_a_sources}

        tenant_b_sources = await retriever.retrieve(
            query=tenant_b_http.content,
            tenant_id="tenant-b",
            limit=5,
        )

        assert [source.document_id for source in tenant_b_sources] == [tenant_b_http.document_id]

        deleted_count = await vector_store.delete_document(
            tenant_id="tenant-a",
            document_id=tenant_a_http.document_id,
        )

        assert deleted_count == 1

        tenant_a_after_delete = await retriever.retrieve(
            query=tenant_a_http.content,
            tenant_id="tenant-a",
            limit=5,
        )

        assert [source.document_id for source in tenant_a_after_delete] == [
            tenant_a_redis.document_id
        ]

        tenant_b_after_delete = await retriever.retrieve(
            query=tenant_b_http.content,
            tenant_id="tenant-b",
            limit=5,
        )

        assert [source.document_id for source in tenant_b_after_delete] == [
            tenant_b_http.document_id
        ]
    finally:
        if await cleanup_client.has_collection(
            collection_name,
        ):
            await cleanup_client.drop_collection(
                collection_name,
            )

        await cleanup_client.close()
        await vector_store.close()
        await embedding_client.close()
