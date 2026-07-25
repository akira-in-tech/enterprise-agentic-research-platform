import math
from collections.abc import Sequence
from hashlib import sha256

from app.services.embeddings.base import (
    EmbeddingVector,
)


class DeterministicEmbeddingClient:
    """Create deterministic vectors for tests and local development.

    These vectors are not semantically meaningful and must not be used
    as a production embedding model.
    """

    def __init__(
        self,
        *,
        dimensions: int = 8,
    ) -> None:
        if dimensions < 1:
            raise ValueError("dimensions must be at least 1.")

        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        """Return the configured embedding dimensions."""

        return self._dimensions

    async def embed_texts(
        self,
        texts: Sequence[str],
    ) -> list[EmbeddingVector]:
        """Create stable unit-length vectors in input order."""

        vectors: list[EmbeddingVector] = []

        for text in texts:
            if not text.strip():
                raise ValueError("Embedding text must not be empty.")

            vectors.append(self._embed_text(text))

        return vectors

    def _embed_text(
        self,
        text: str,
    ) -> EmbeddingVector:
        values: EmbeddingVector = []
        counter = 0
        maximum_uint32 = float((1 << 32) - 1)

        while len(values) < self._dimensions:
            digest = sha256(f"{counter}\0{text}".encode()).digest()

            for offset in range(0, len(digest), 4):
                integer = int.from_bytes(
                    digest[offset : offset + 4],
                    byteorder="big",
                )
                value = (integer / maximum_uint32) * 2.0 - 1.0
                values.append(value)

                if len(values) == self._dimensions:
                    break

            counter += 1

        magnitude = math.sqrt(sum(value * value for value in values))

        return [value / magnitude for value in values]
