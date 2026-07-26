from dataclasses import dataclass

from app.schemas.document import PrivateDocument
from app.services.embeddings.base import (
    EmbeddingClient,
)
from app.services.knowledge.chunking import (
    chunk_document,
)
from app.services.vector_store.base import (
    VectorRecord,
    VectorStore,
)


@dataclass(frozen=True, slots=True)
class DocumentIndexResult:
    """Summarize one completed document indexing operation."""

    document_id: str
    chunk_count: int
    vector_dimensions: int


class KnowledgeIndexer:
    """Chunk, embed, and store one private document."""

    def __init__(
        self,
        embedding_client: EmbeddingClient,
        vector_store: VectorStore,
        *,
        max_words: int = 200,
        overlap_words: int = 30,
        embedding_batch_size: int = 32,
    ) -> None:
        if max_words < 1:
            raise ValueError("max_words must be greater than 0.")

        if overlap_words < 0:
            raise ValueError("overlap_words must not be negative.")

        if overlap_words >= max_words:
            raise ValueError("overlap_words must be less than max_words.")

        if embedding_batch_size < 1:
            raise ValueError("embedding_batch_size must be at least 1.")

        if embedding_client.dimensions != vector_store.dimensions:
            raise ValueError("Embedding client and vector store dimensions must match.")

        self._embedding_client = embedding_client
        self._vector_store = vector_store
        self._max_words = max_words
        self._overlap_words = overlap_words
        self._embedding_batch_size = embedding_batch_size

    async def index_document(
        self,
        document: PrivateDocument,
    ) -> DocumentIndexResult:
        """Index one document without partial vector writes."""

        chunks = chunk_document(
            document,
            max_words=self._max_words,
            overlap_words=self._overlap_words,
        )

        embeddings: list[list[float]] = []

        for batch_start in range(
            0,
            len(chunks),
            self._embedding_batch_size,
        ):
            batch_chunks = chunks[batch_start : (batch_start + self._embedding_batch_size)]
            batch_texts = [chunk.content for chunk in batch_chunks]

            batch_embeddings = await self._embedding_client.embed_texts(batch_texts)

            if len(batch_embeddings) != len(batch_chunks):
                raise RuntimeError(
                    "Embedding provider returned "
                    f"{len(batch_embeddings)} vectors for "
                    f"{len(batch_chunks)} texts."
                )

            for embedding in batch_embeddings:
                if len(embedding) != (self._embedding_client.dimensions):
                    raise RuntimeError(
                        "Embedding provider returned a vector "
                        f"with {len(embedding)} dimensions; "
                        "expected "
                        f"{self._embedding_client.dimensions}."
                    )

            embeddings.extend(batch_embeddings)

        records = [
            VectorRecord(
                chunk=chunk,
                embedding=tuple(embedding),
            )
            for chunk, embedding in zip(
                chunks,
                embeddings,
                strict=True,
            )
        ]

        await self._vector_store.upsert(records)

        return DocumentIndexResult(
            document_id=document.document_id,
            chunk_count=len(chunks),
            vector_dimensions=(self._embedding_client.dimensions),
        )
