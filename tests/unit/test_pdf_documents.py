from io import BytesIO

import pytest
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen.canvas import (  # type: ignore[import-untyped]
    Canvas,
)

from app.services.knowledge.chunking import (
    chunk_document,
)
from app.services.knowledge.pdfs import (
    create_pdf_document,
)


def create_pdf_bytes(
    page_texts: list[str],
) -> bytes:
    """Create a small in-memory PDF fixture."""

    buffer = BytesIO()
    canvas = Canvas(buffer)

    for page_text in page_texts:
        if page_text:
            canvas.drawString(
                72,
                720,
                page_text,
            )

        canvas.showPage()

    canvas.save()

    return buffer.getvalue()


def encrypt_pdf(
    raw_content: bytes,
) -> bytes:
    """Encrypt an in-memory PDF fixture."""

    reader = PdfReader(BytesIO(raw_content))
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)
    writer.encrypt("test-password")

    buffer = BytesIO()
    writer.write(buffer)

    return buffer.getvalue()


def test_create_pdf_document_extracts_text() -> None:
    raw_content = create_pdf_bytes(
        [
            "HTTP keep-alive reuses a connection.",
            "HTTP/2 supports multiplexed streams.",
        ]
    )

    first_document = create_pdf_document(
        tenant_id="tenant-hennge",
        filename="http-notes.pdf",
        raw_content=raw_content,
    )
    second_document = create_pdf_document(
        tenant_id="tenant-hennge",
        filename="http-notes.pdf",
        raw_content=raw_content,
    )

    assert first_document == second_document
    assert first_document.media_type == ("application/pdf")
    assert "HTTP keep-alive" in first_document.content
    assert "HTTP/2" in first_document.content

    chunks = chunk_document(
        first_document,
        max_words=6,
        overlap_words=1,
    )

    assert chunks
    assert all(chunk.document_id == first_document.document_id for chunk in chunks)


def test_create_pdf_document_rejects_scanned_pdf() -> None:
    raw_content = create_pdf_bytes([""])

    with pytest.raises(
        ValueError,
        match="no extractable text",
    ):
        create_pdf_document(
            tenant_id="tenant-hennge",
            filename="scanned.pdf",
            raw_content=raw_content,
        )


def test_create_pdf_document_rejects_encrypted_pdf() -> None:
    raw_content = encrypt_pdf(create_pdf_bytes(["Private infrastructure notes."]))

    with pytest.raises(
        ValueError,
        match="Encrypted PDF",
    ):
        create_pdf_document(
            tenant_id="tenant-hennge",
            filename="encrypted.pdf",
            raw_content=raw_content,
        )


def test_create_pdf_document_rejects_invalid_bytes() -> None:
    with pytest.raises(
        ValueError,
        match="Could not read",
    ):
        create_pdf_document(
            tenant_id="tenant-hennge",
            filename="invalid.pdf",
            raw_content=b"This is not a PDF.",
        )


def test_create_pdf_document_requires_pdf_extension() -> None:
    with pytest.raises(
        ValueError,
        match="must end with .pdf",
    ):
        create_pdf_document(
            tenant_id="tenant-hennge",
            filename="notes.txt",
            raw_content=b"Not parsed.",
        )
