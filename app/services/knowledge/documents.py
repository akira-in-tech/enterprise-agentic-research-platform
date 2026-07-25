from hashlib import sha256
from pathlib import Path

from app.schemas.document import (
    DocumentMediaType,
    PrivateDocument,
)

SUPPORTED_MEDIA_TYPES: dict[
    str,
    DocumentMediaType,
] = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
}


def create_text_document(
    *,
    tenant_id: str,
    filename: str,
    raw_content: bytes,
    max_bytes: int = 2_000_000,
) -> PrivateDocument:
    """Validate and create a private text document."""

    normalized_tenant_id = tenant_id.strip()
    normalized_filename = filename.strip()

    if not normalized_tenant_id:
        raise ValueError("Tenant ID must not be empty.")

    if not normalized_filename:
        raise ValueError("Document filename must not be empty.")

    if (
        "/" in normalized_filename
        or "\\" in normalized_filename
    ):
        raise ValueError(
            "Document filename must not include a path."
        )

    if max_bytes < 1:
        raise ValueError(
            "max_bytes must be greater than 0."
        )

    if len(raw_content) > max_bytes:
        raise ValueError(
            "Document exceeds the maximum allowed size."
        )

    extension = Path(
        normalized_filename
    ).suffix.casefold()

    media_type = SUPPORTED_MEDIA_TYPES.get(
        extension
    )

    if media_type is None:
        raise ValueError(
            "Unsupported document extension. "
            "Expected .txt, .md, or .markdown."
        )

    try:
        decoded_content = raw_content.decode(
            "utf-8-sig"
        )
    except UnicodeDecodeError as error:
        raise ValueError(
            "Document must contain valid UTF-8 text."
        ) from error

    normalized_content = (
        decoded_content
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .strip()
    )

    if not normalized_content:
        raise ValueError(
            "Document content must not be empty."
        )

    if "\x00" in normalized_content:
        raise ValueError(
            "Document must not contain null bytes."
        )

    content_sha256 = sha256(
        normalized_content.encode("utf-8")
    ).hexdigest()

    identity = "\0".join(
        (
            normalized_tenant_id,
            normalized_filename,
            content_sha256,
        )
    )
    document_digest = sha256(
        identity.encode("utf-8")
    ).hexdigest()[:16].upper()

    return PrivateDocument(
        document_id=f"DOC-{document_digest}",
        tenant_id=normalized_tenant_id,
        filename=normalized_filename,
        media_type=media_type,
        content=normalized_content,
        content_sha256=content_sha256,
    )