from typing import Protocol

from app.core.config import settings
from app.services.embeddings.base import EmbeddingClient
from app.services.embeddings.bedrock import BedrockTitanEmbeddingClient
from app.services.embeddings.ollama import OllamaEmbeddingClient


class ClosableEmbeddingClient(EmbeddingClient, Protocol):
    async def close(self) -> None: ...


def create_embedding_client(provider: str | None = None) -> ClosableEmbeddingClient:
    """Create the configured local or AWS embedding provider."""

    selected_provider = (provider or settings.embedding_provider).strip().lower()
    if selected_provider == "ollama":
        return OllamaEmbeddingClient()
    if selected_provider == "bedrock":
        return BedrockTitanEmbeddingClient()
    raise ValueError(
        f"Unsupported embedding provider: {selected_provider}. Expected 'ollama' or 'bedrock'."
    )
