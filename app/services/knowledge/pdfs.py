from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.schemas.document import PrivateDocument
from app.services.knowledge.documents import (
    create_private_document,
)


def create_pdf_document(
    *,
    tenant_id: str,
    filename: str,
    raw_content: bytes,
    max_bytes: int = 10_000_000,
    max_pages: int = 200,
) -> PrivateDocument:
    """Extract text and create a private PDF document."""

    normalized_filename = filename.strip()

    if Path(normalized_filename).suffix.casefold() != ".pdf":
        raise ValueError("PDF document filename must end with .pdf.")

    if max_bytes < 1:
        raise ValueError("max_bytes must be greater than 0.")

    if max_pages < 1:
        raise ValueError("max_pages must be greater than 0.")

    if not raw_content:
        raise ValueError("PDF content must not be empty.")

    if len(raw_content) > max_bytes:
        raise ValueError("PDF exceeds the maximum allowed size.")

    try:
        reader = PdfReader(BytesIO(raw_content))
    except (PdfReadError, ValueError, OSError) as error:
        raise ValueError("Could not read the PDF document.") from error

    if reader.is_encrypted:
        raise ValueError("Encrypted PDF documents are not supported.")

    page_count = len(reader.pages)

    if page_count == 0:
        raise ValueError("PDF document contains no pages.")

    if page_count > max_pages:
        raise ValueError("PDF exceeds the maximum allowed page count.")

    page_texts: list[str] = []

    for page_number, page in enumerate(
        reader.pages,
        start=1,
    ):
        try:
            page_text = (page.extract_text() or "").strip()
        except Exception as error:
            raise ValueError(f"Could not extract text from PDF page {page_number}.") from error

        if page_text:
            page_texts.append(page_text)

    if not page_texts:
        raise ValueError(
            "PDF contains no extractable text. It may be a scanned document that requires OCR."
        )

    return create_private_document(
        tenant_id=tenant_id,
        filename=normalized_filename,
        media_type="application/pdf",
        content="\n\n".join(page_texts),
    )
