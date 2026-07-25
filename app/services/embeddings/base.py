from collections.abc import Sequence
from typing import Protocol

type EmbeddingVector = list[float]


class EmbeddingClient(Protocol):
    """Define the behavior required from an embedding provider."""

    @property
    def dimensions(self) -> int:
        """Return the number of values in each embedding vector."""
        ...

    async def embed_texts(
        self,
        texts: Sequence[str],
    ) -> list[EmbeddingVector]:
        """Create one embedding vector for each input text."""
        ...
