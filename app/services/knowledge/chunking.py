from hashlib import sha256

from app.schemas.document import (
    DocumentChunk,
    PrivateDocument,
)


def chunk_document(
    document: PrivateDocument,
    *,
    max_words: int = 200,
    overlap_words: int = 30,
) -> list[DocumentChunk]:
    """Split a document into deterministic overlapping chunks."""

    if max_words < 1:
        raise ValueError("max_words must be greater than 0.")

    if overlap_words < 0:
        raise ValueError("overlap_words must not be negative.")

    if overlap_words >= max_words:
        raise ValueError("overlap_words must be less than max_words.")

    words = document.content.split()
    step = max_words - overlap_words
    chunks: list[DocumentChunk] = []

    for position, word_start in enumerate(range(0, len(words), step)):
        word_end = min(
            word_start + max_words,
            len(words),
        )
        chunk_content = " ".join(words[word_start:word_end])

        identity = "\0".join(
            (
                document.document_id,
                str(position),
                chunk_content,
            )
        )
        chunk_digest = sha256(identity.encode("utf-8")).hexdigest()[:16].upper()

        chunks.append(
            DocumentChunk(
                chunk_id=f"CHK-{chunk_digest}",
                document_id=document.document_id,
                tenant_id=document.tenant_id,
                filename=document.filename,
                media_type=document.media_type,
                position=position,
                word_start=word_start,
                word_end=word_end,
                content=chunk_content,
            )
        )

        if word_end == len(words):
            break

    return chunks
