import pytest

from app.services.knowledge.chunking import (
    chunk_document,
)
from app.services.knowledge.documents import (
    create_text_document,
)


def test_create_text_document_is_deterministic() -> None:
    first_document = create_text_document(
        tenant_id="tenant-hennge",
        filename="architecture.MD",
        raw_content=(b"\xef\xbb\xbf# Architecture\r\n\r\nHTTP and networking notes.\r\n"),
    )
    second_document = create_text_document(
        tenant_id="tenant-hennge",
        filename="architecture.MD",
        raw_content=(b"# Architecture\n\nHTTP and networking notes.\n"),
    )

    assert first_document == second_document
    assert first_document.document_id.startswith("DOC-")
    assert first_document.media_type == ("text/markdown")
    assert "\r" not in first_document.content


@pytest.mark.parametrize(
    "filename",
    [
        "notes.pdf",
        "notes.exe",
        "../notes.txt",
    ],
)
def test_create_text_document_rejects_invalid_filename(
    filename: str,
) -> None:
    with pytest.raises(ValueError):
        create_text_document(
            tenant_id="tenant-hennge",
            filename=filename,
            raw_content=b"Valid text content.",
        )


def test_create_text_document_rejects_empty_content() -> None:
    with pytest.raises(
        ValueError,
        match="Document content must not be empty",
    ):
        create_text_document(
            tenant_id="tenant-hennge",
            filename="empty.txt",
            raw_content=b"   \n",
        )


def test_chunk_document_is_deterministic() -> None:
    document = create_text_document(
        tenant_id="tenant-hennge",
        filename="networking.md",
        raw_content=(b"one two three four five six seven eight nine ten"),
    )

    first_chunks = chunk_document(
        document,
        max_words=4,
        overlap_words=1,
    )
    second_chunks = chunk_document(
        document,
        max_words=4,
        overlap_words=1,
    )

    assert first_chunks == second_chunks
    assert len(first_chunks) == 3

    assert first_chunks[0].content == ("one two three four")
    assert first_chunks[0].word_start == 0
    assert first_chunks[0].word_end == 4

    assert first_chunks[1].content == ("four five six seven")
    assert first_chunks[1].word_start == 3
    assert first_chunks[1].word_end == 7

    assert first_chunks[2].content == ("seven eight nine ten")
    assert first_chunks[2].word_start == 6
    assert first_chunks[2].word_end == 10

    assert len({chunk.chunk_id for chunk in first_chunks}) == 3


@pytest.mark.parametrize(
    ("max_words", "overlap_words"),
    [
        (0, 0),
        (4, -1),
        (4, 4),
    ],
)
def test_chunk_document_rejects_invalid_parameters(
    max_words: int,
    overlap_words: int,
) -> None:
    document = create_text_document(
        tenant_id="tenant-hennge",
        filename="networking.txt",
        raw_content=b"one two three four",
    )

    with pytest.raises(ValueError):
        chunk_document(
            document,
            max_words=max_words,
            overlap_words=overlap_words,
        )
