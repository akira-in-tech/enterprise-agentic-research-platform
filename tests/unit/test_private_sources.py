import pytest

from app.schemas.document import DocumentChunk
from app.services.knowledge.chunking import (
    chunk_document,
)
from app.services.knowledge.documents import (
    create_text_document,
)
from app.services.knowledge.sources import (
    build_private_source_pool,
    create_private_source_id,
)
from app.services.vector_store.base import (
    VectorSearchResult,
)


def create_test_chunk() -> DocumentChunk:
    document = create_text_document(
        tenant_id="tenant-hennge",
        filename="networking.md",
        raw_content=(b"HTTP keep-alive reduces repeated connection setup overhead."),
    )

    return chunk_document(
        document,
        max_words=20,
        overlap_words=0,
    )[0]


def test_chunk_preserves_document_metadata() -> None:
    document = create_text_document(
        tenant_id="tenant-hennge",
        filename="architecture.md",
        raw_content=(b"Distributed systems architecture notes."),
    )

    chunk = chunk_document(
        document,
        max_words=20,
        overlap_words=0,
    )[0]

    assert chunk.filename == "architecture.md"
    assert chunk.media_type == "text/markdown"


def test_private_source_id_is_stable() -> None:
    chunk = create_test_chunk()

    first_id = create_private_source_id(chunk.chunk_id)
    second_id = create_private_source_id(chunk.chunk_id.lower())

    assert first_id == second_id
    assert first_id.startswith("PRIVATE-")
    assert len(first_id) == 24


@pytest.mark.parametrize(
    "chunk_id",
    [
        "",
        "DOC-1234567890ABCDEF",
        "CHK-invalid",
    ],
)
def test_private_source_id_rejects_invalid_chunk_id(
    chunk_id: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="Invalid chunk ID",
    ):
        create_private_source_id(chunk_id)


def test_build_private_source_pool_maps_and_deduplicates() -> None:
    chunk = create_test_chunk()

    private_sources = build_private_source_pool(
        [
            VectorSearchResult(
                chunk=chunk,
                score=0.95,
            ),
            VectorSearchResult(
                chunk=chunk,
                score=0.80,
            ),
        ]
    )

    assert len(private_sources) == 1

    source = private_sources[0]

    assert source.source_id == (create_private_source_id(chunk.chunk_id))
    assert source.document_id == (chunk.document_id)
    assert source.chunk_id == chunk.chunk_id
    assert source.filename == "networking.md"
    assert source.media_type == "text/markdown"
    assert source.content == chunk.content
    assert source.score == pytest.approx(0.95)
    assert source.provider == "private_knowledge"
