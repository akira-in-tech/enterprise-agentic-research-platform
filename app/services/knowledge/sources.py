import re
from collections.abc import Iterable

from app.schemas.source import PrivateSource
from app.services.vector_store.base import (
    VectorSearchResult,
)

CHUNK_ID_PATTERN = re.compile(r"^CHK-([0-9A-F]{16})$")


def create_private_source_id(
    chunk_id: str,
) -> str:
    """Create a stable private source ID from a chunk ID."""

    normalized_chunk_id = chunk_id.strip().upper()
    match = CHUNK_ID_PATTERN.fullmatch(normalized_chunk_id)

    if match is None:
        raise ValueError("Invalid chunk ID.")

    return f"PRIVATE-{match.group(1)}"


def build_private_source_pool(
    matches: Iterable[VectorSearchResult],
) -> list[PrivateSource]:
    """Build canonical deduplicated private sources."""

    seen_source_ids: set[str] = set()
    private_sources: list[PrivateSource] = []

    for match in matches:
        source_id = create_private_source_id(match.chunk.chunk_id)

        if source_id in seen_source_ids:
            continue

        seen_source_ids.add(source_id)

        private_sources.append(
            PrivateSource(
                source_id=source_id,
                document_id=(match.chunk.document_id),
                chunk_id=match.chunk.chunk_id,
                filename=match.chunk.filename,
                media_type=match.chunk.media_type,
                content=match.chunk.content,
                score=match.score,
            )
        )

    return private_sources
