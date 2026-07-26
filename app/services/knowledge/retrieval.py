from app.schemas.source import PrivateSource
from app.services.embeddings.base import (
    EmbeddingClient,
)
from app.services.knowledge.sources import (
    build_private_source_pool,
)
from app.services.vector_store.base import (
    VectorStore,
)


class PrivateKnowledgeRetriever:
    """Retrieve tenant-scoped private knowledge sources."""

    def __init__(
        self,
        embedding_client: EmbeddingClient,
        vector_store: VectorStore,
    ) -> None:
        if embedding_client.dimensions != vector_store.dimensions:
            raise ValueError("Embedding client and vector store dimensions must match.")

        self._embedding_client = embedding_client
        self._vector_store = vector_store

    async def retrieve(
        self,
        *,
        query: str,
        tenant_id: str,
        limit: int = 5,
    ) -> list[PrivateSource]:
        """Embed a query and return ranked private sources."""

        normalized_query = query.strip()
        normalized_tenant_id = tenant_id.strip()

        if not normalized_query:
            raise ValueError("query must not be empty.")

        if not normalized_tenant_id:
            raise ValueError("tenant_id must not be empty.")

        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100.")

        query_embeddings = await self._embedding_client.embed_texts(
            [
                normalized_query,
            ]
        )

        if len(query_embeddings) != 1:
            raise RuntimeError(
                f"Embedding provider returned {len(query_embeddings)} vectors for 1 query."
            )

        query_vector = query_embeddings[0]

        if len(query_vector) != (self._embedding_client.dimensions):
            raise RuntimeError(
                "Embedding provider returned a query "
                f"vector with {len(query_vector)} "
                "dimensions; expected "
                f"{self._embedding_client.dimensions}."
            )

        matches = await self._vector_store.search(
            tenant_id=normalized_tenant_id,
            query_vector=query_vector,
            limit=limit,
        )

        return build_private_source_pool(matches)
