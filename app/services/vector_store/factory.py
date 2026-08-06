from app.core.circuit_breaker import CircuitBreaker
from app.core.config import settings
from app.services.vector_store.base import VectorStore
from app.services.vector_store.memory import (
    InMemoryVectorStore,
)
from app.services.vector_store.milvus import (
    MilvusVectorStore,
)


def create_vector_store(
    provider: str | None = None,
    *,
    dimensions: int | None = None,
) -> VectorStore:
    """Create the configured vector-store provider."""

    selected_provider = (provider or settings.vector_store_provider).strip().lower()

    selected_dimensions = (
        dimensions if dimensions is not None else settings.ollama_embedding_dimensions
    )

    if selected_provider == "memory":
        return InMemoryVectorStore(
            dimensions=selected_dimensions,
        )

    if selected_provider == "milvus":
        return MilvusVectorStore(
            dimensions=selected_dimensions,
            circuit_breaker=CircuitBreaker(),
        )

    raise ValueError(
        f"Unsupported vector-store provider: {selected_provider}. Expected 'memory' or 'milvus'."
    )
