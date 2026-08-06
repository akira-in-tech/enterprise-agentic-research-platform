import asyncio
from collections.abc import Sequence

import pytest

from app.schemas.document import DocumentChunk
from app.services.embeddings.deterministic import (
    DeterministicEmbeddingClient,
)
from app.services.knowledge.chunking import (
    chunk_document,
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
from app.services.vector_store.base import (
    VectorRecord,
)
from app.services.vector_store.memory import (
    InMemoryVectorStore,
)


class StubEmbeddingClient:
    """Return configured query embeddings."""

    def __init__(
        self,
        embeddings: Sequence[Sequence[float]],
        *,
        dimensions: int = 2,
    ) -> None:
        self._dimensions = dimensions
        self._embeddings = [list(embedding) for embedding in embeddings]
        self.calls: list[list[str]] = []

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed_texts(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        self.calls.append(list(texts))

        return [list(embedding) for embedding in self._embeddings]


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


def test_retrieve_returns_exact_indexed_chunk_first() -> None:
    document = create_text_document(
        tenant_id="tenant-acme",
        filename="networking.md",
        raw_content=(
            b"HTTP connection reuse improves latency. DNS caching reduces repeated lookups."
        ),
    )
    embedding_client = DeterministicEmbeddingClient(
        dimensions=8,
    )
    vector_store = InMemoryVectorStore(
        dimensions=8,
    )
    indexer = KnowledgeIndexer(
        embedding_client,
        vector_store,
        max_words=5,
        overlap_words=0,
    )
    retriever = PrivateKnowledgeRetriever(
        embedding_client,
        vector_store,
    )

    asyncio.run(indexer.index_document(document))

    chunks = chunk_document(
        document,
        max_words=5,
        overlap_words=0,
    )

    sources = asyncio.run(
        retriever.retrieve(
            query=chunks[1].content,
            tenant_id="tenant-acme",
            limit=2,
        )
    )

    assert sources[0].chunk_id == (chunks[1].chunk_id)
    assert sources[0].filename == "networking.md"
    assert sources[0].score == pytest.approx(1.0)
    assert sources[0].source_id.startswith("PRIVATE-")


def test_retrieve_enforces_tenant_isolation() -> None:
    tenant_a_chunk = create_test_chunk(
        tenant_id="tenant-a",
        filename="private-a.md",
        content="Tenant A private network design.",
    )
    tenant_b_chunk = create_test_chunk(
        tenant_id="tenant-b",
        filename="private-b.md",
        content="Tenant B private network design.",
    )
    vector_store = InMemoryVectorStore(
        dimensions=2,
    )

    asyncio.run(
        vector_store.upsert(
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

    embedding_client = StubEmbeddingClient(
        [
            [1.0, 0.0],
        ]
    )
    retriever = PrivateKnowledgeRetriever(
        embedding_client,
        vector_store,
    )

    sources = asyncio.run(
        retriever.retrieve(
            query="private network design",
            tenant_id="tenant-a",
        )
    )

    assert len(sources) == 1
    assert sources[0].chunk_id == (tenant_a_chunk.chunk_id)
    assert sources[0].filename == "private-a.md"


def test_retrieve_preserves_ranking_and_limit() -> None:
    exact_chunk = create_test_chunk(
        tenant_id="tenant-acme",
        filename="exact.md",
        content="Exact PostgreSQL indexing evidence.",
    )
    related_chunk = create_test_chunk(
        tenant_id="tenant-acme",
        filename="related.md",
        content="Related database indexing evidence.",
    )
    unrelated_chunk = create_test_chunk(
        tenant_id="tenant-acme",
        filename="unrelated.md",
        content="Unrelated Redis persistence evidence.",
    )
    vector_store = InMemoryVectorStore(
        dimensions=2,
    )

    asyncio.run(
        vector_store.upsert(
            [
                VectorRecord(
                    chunk=exact_chunk,
                    embedding=(1.0, 0.0),
                ),
                VectorRecord(
                    chunk=related_chunk,
                    embedding=(0.8, 0.2),
                ),
                VectorRecord(
                    chunk=unrelated_chunk,
                    embedding=(0.0, 1.0),
                ),
            ]
        )
    )

    embedding_client = StubEmbeddingClient(
        [
            [1.0, 0.0],
        ]
    )
    retriever = PrivateKnowledgeRetriever(
        embedding_client,
        vector_store,
    )

    sources = asyncio.run(
        retriever.retrieve(
            query="PostgreSQL indexing",
            tenant_id="tenant-acme",
            limit=2,
        )
    )

    assert [source.chunk_id for source in sources] == [
        exact_chunk.chunk_id,
        related_chunk.chunk_id,
    ]


def test_retrieve_scopes_to_the_given_documents() -> None:
    allowed_chunk = create_test_chunk(
        tenant_id="tenant-acme",
        filename="allowed.md",
        content="Allowed document content.",
    )
    excluded_chunk = create_test_chunk(
        tenant_id="tenant-acme",
        filename="excluded.md",
        content="Excluded document content.",
    )
    vector_store = InMemoryVectorStore(
        dimensions=2,
    )

    asyncio.run(
        vector_store.upsert(
            [
                VectorRecord(
                    chunk=allowed_chunk,
                    embedding=(1.0, 0.0),
                ),
                VectorRecord(
                    chunk=excluded_chunk,
                    embedding=(1.0, 0.0),
                ),
            ]
        )
    )

    embedding_client = StubEmbeddingClient(
        [
            [1.0, 0.0],
        ]
    )
    retriever = PrivateKnowledgeRetriever(
        embedding_client,
        vector_store,
    )

    sources = asyncio.run(
        retriever.retrieve(
            query="document content",
            tenant_id="tenant-acme",
            document_ids=[allowed_chunk.document_id],
        )
    )

    assert [source.chunk_id for source in sources] == [allowed_chunk.chunk_id]


def test_retrieve_from_empty_store_returns_empty_list() -> None:
    embedding_client = StubEmbeddingClient(
        [
            [1.0, 0.0],
        ]
    )
    vector_store = InMemoryVectorStore(
        dimensions=2,
    )
    retriever = PrivateKnowledgeRetriever(
        embedding_client,
        vector_store,
    )

    sources = asyncio.run(
        retriever.retrieve(
            query="Linux epoll",
            tenant_id="tenant-acme",
        )
    )

    assert sources == []


def test_retriever_rejects_dimension_mismatch() -> None:
    embedding_client = StubEmbeddingClient(
        [
            [1.0, 0.0],
        ],
        dimensions=2,
    )
    vector_store = InMemoryVectorStore(
        dimensions=3,
    )

    with pytest.raises(
        ValueError,
        match=("Embedding client and vector store dimensions must match"),
    ):
        PrivateKnowledgeRetriever(
            embedding_client,
            vector_store,
        )


def test_retrieve_rejects_wrong_embedding_count() -> None:
    embedding_client = StubEmbeddingClient(
        [],
        dimensions=2,
    )
    vector_store = InMemoryVectorStore(
        dimensions=2,
    )
    retriever = PrivateKnowledgeRetriever(
        embedding_client,
        vector_store,
    )

    with pytest.raises(
        RuntimeError,
        match="returned 0 vectors for 1 query",
    ):
        asyncio.run(
            retriever.retrieve(
                query="Explain DNS caching.",
                tenant_id="tenant-acme",
            )
        )


def test_retrieve_rejects_wrong_vector_dimensions() -> None:
    embedding_client = StubEmbeddingClient(
        [
            [1.0],
        ],
        dimensions=2,
    )
    vector_store = InMemoryVectorStore(
        dimensions=2,
    )
    retriever = PrivateKnowledgeRetriever(
        embedding_client,
        vector_store,
    )

    with pytest.raises(
        RuntimeError,
        match="with 1 dimensions; expected 2",
    ):
        asyncio.run(
            retriever.retrieve(
                query="Explain DNS caching.",
                tenant_id="tenant-acme",
            )
        )


@pytest.mark.parametrize(
    (
        "query",
        "tenant_id",
        "limit",
        "expected_error",
    ),
    [
        (
            "",
            "tenant-acme",
            5,
            "query must not be empty",
        ),
        (
            "   ",
            "tenant-acme",
            5,
            "query must not be empty",
        ),
        (
            "Explain HTTP keep-alive.",
            "",
            5,
            "tenant_id must not be empty",
        ),
        (
            "Explain HTTP keep-alive.",
            "tenant-acme",
            0,
            "limit must be between 1 and 100",
        ),
        (
            "Explain HTTP keep-alive.",
            "tenant-acme",
            101,
            "limit must be between 1 and 100",
        ),
    ],
)
def test_retrieve_validates_request_before_embedding(
    query: str,
    tenant_id: str,
    limit: int,
    expected_error: str,
) -> None:
    embedding_client = StubEmbeddingClient(
        [
            [1.0, 0.0],
        ]
    )
    vector_store = InMemoryVectorStore(
        dimensions=2,
    )
    retriever = PrivateKnowledgeRetriever(
        embedding_client,
        vector_store,
    )

    with pytest.raises(
        ValueError,
        match=expected_error,
    ):
        asyncio.run(
            retriever.retrieve(
                query=query,
                tenant_id=tenant_id,
                limit=limit,
            )
        )

    assert embedding_client.calls == []
