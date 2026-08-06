import asyncio
from collections.abc import Sequence

import pytest

from app.schemas.document import PrivateDocument
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
from app.services.vector_store.memory import (
    InMemoryVectorStore,
)


class RecordingEmbeddingClient:
    """Provide controllable embeddings for indexing tests."""

    def __init__(
        self,
        *,
        dimensions: int = 3,
        fail_on_call: int | None = None,
        return_too_few: bool = False,
        returned_dimensions: int | None = None,
    ) -> None:
        self._dimensions = dimensions
        self.fail_on_call = fail_on_call
        self.return_too_few = return_too_few
        self.returned_dimensions = (
            returned_dimensions if returned_dimensions is not None else dimensions
        )
        self.calls: list[list[str]] = []

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed_texts(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        self.calls.append(list(texts))

        if self.fail_on_call is not None and len(self.calls) == self.fail_on_call:
            raise RuntimeError("Simulated embedding failure.")

        vectors = [
            [
                float((sum(text.encode()) + position) % 97 + 1)
                for position in range(self.returned_dimensions)
            ]
            for text in texts
        ]

        if self.return_too_few:
            return vectors[:-1]

        return vectors


def create_test_document() -> PrivateDocument:
    return create_text_document(
        tenant_id="tenant-acme",
        filename="distributed-systems.md",
        raw_content=(b"one two three four five six seven eight nine ten"),
    )


def test_index_document_batches_and_stores_all_chunks() -> None:
    document = create_test_document()
    embedding_client = RecordingEmbeddingClient(
        dimensions=3,
    )
    vector_store = InMemoryVectorStore(
        dimensions=3,
    )
    indexer = KnowledgeIndexer(
        embedding_client,
        vector_store,
        max_words=3,
        overlap_words=0,
        embedding_batch_size=2,
    )

    result = asyncio.run(indexer.index_document(document))

    matches = asyncio.run(
        vector_store.search(
            tenant_id="tenant-acme",
            query_vector=(1.0, 1.0, 1.0),
            limit=100,
        )
    )

    assert result.document_id == (document.document_id)
    assert result.chunk_count == 4
    assert result.vector_dimensions == 3
    assert [len(batch) for batch in embedding_client.calls] == [2, 2]
    assert len(matches) == 4


def test_indexed_chunk_can_be_retrieved_by_exact_embedding() -> None:
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

    asyncio.run(indexer.index_document(document))

    chunks = chunk_document(
        document,
        max_words=5,
        overlap_words=0,
    )
    query_vector = asyncio.run(
        embedding_client.embed_texts(
            [
                chunks[1].content,
            ]
        )
    )[0]

    matches = asyncio.run(
        vector_store.search(
            tenant_id="tenant-acme",
            query_vector=query_vector,
            limit=2,
        )
    )

    assert matches[0].chunk.chunk_id == (chunks[1].chunk_id)
    assert matches[0].score == pytest.approx(1.0)


def test_indexer_rejects_dimension_mismatch() -> None:
    embedding_client = RecordingEmbeddingClient(
        dimensions=3,
    )
    vector_store = InMemoryVectorStore(
        dimensions=4,
    )

    with pytest.raises(
        ValueError,
        match=("Embedding client and vector store dimensions must match"),
    ):
        KnowledgeIndexer(
            embedding_client,
            vector_store,
        )


def test_indexing_rejects_wrong_embedding_count() -> None:
    document = create_test_document()
    embedding_client = RecordingEmbeddingClient(
        dimensions=3,
        return_too_few=True,
    )
    vector_store = InMemoryVectorStore(
        dimensions=3,
    )
    indexer = KnowledgeIndexer(
        embedding_client,
        vector_store,
        max_words=5,
        overlap_words=0,
    )

    with pytest.raises(
        RuntimeError,
        match="returned 1 vectors for 2 texts",
    ):
        asyncio.run(indexer.index_document(document))

    matches = asyncio.run(
        vector_store.search(
            tenant_id="tenant-acme",
            query_vector=(1.0, 1.0, 1.0),
        )
    )

    assert matches == []


def test_indexing_rejects_wrong_vector_dimensions() -> None:
    document = create_test_document()
    embedding_client = RecordingEmbeddingClient(
        dimensions=3,
        returned_dimensions=2,
    )
    vector_store = InMemoryVectorStore(
        dimensions=3,
    )
    indexer = KnowledgeIndexer(
        embedding_client,
        vector_store,
        max_words=10,
        overlap_words=0,
    )

    with pytest.raises(
        RuntimeError,
        match="with 2 dimensions; expected 3",
    ):
        asyncio.run(indexer.index_document(document))


def test_embedding_failure_does_not_partially_write() -> None:
    document = create_test_document()
    embedding_client = RecordingEmbeddingClient(
        dimensions=3,
        fail_on_call=2,
    )
    vector_store = InMemoryVectorStore(
        dimensions=3,
    )
    indexer = KnowledgeIndexer(
        embedding_client,
        vector_store,
        max_words=3,
        overlap_words=0,
        embedding_batch_size=2,
    )

    with pytest.raises(
        RuntimeError,
        match="Simulated embedding failure",
    ):
        asyncio.run(indexer.index_document(document))

    matches = asyncio.run(
        vector_store.search(
            tenant_id="tenant-acme",
            query_vector=(1.0, 1.0, 1.0),
        )
    )

    assert matches == []


@pytest.mark.parametrize(
    ("max_words", "overlap_words"),
    [
        (0, 0),
        (4, -1),
        (4, 4),
    ],
)
def test_indexer_rejects_invalid_chunk_configuration(
    max_words: int,
    overlap_words: int,
) -> None:
    embedding_client = RecordingEmbeddingClient()
    vector_store = InMemoryVectorStore(
        dimensions=3,
    )

    with pytest.raises(ValueError):
        KnowledgeIndexer(
            embedding_client,
            vector_store,
            max_words=max_words,
            overlap_words=overlap_words,
        )


@pytest.mark.parametrize(
    "embedding_batch_size",
    [
        0,
        -1,
    ],
)
def test_indexer_rejects_invalid_batch_size(
    embedding_batch_size: int,
) -> None:
    embedding_client = RecordingEmbeddingClient()
    vector_store = InMemoryVectorStore(
        dimensions=3,
    )

    with pytest.raises(
        ValueError,
        match=("embedding_batch_size must be at least 1"),
    ):
        KnowledgeIndexer(
            embedding_client,
            vector_store,
            embedding_batch_size=(embedding_batch_size),
        )
