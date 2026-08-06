from typing import Protocol

from app.core.config import settings
from app.services.storage.base import DocumentStorage
from app.services.storage.filesystem import LocalDocumentStorage
from app.services.storage.s3 import S3DocumentStorage


class ClosableDocumentStorage(DocumentStorage, Protocol):
    async def close(self) -> None: ...


def create_document_storage(provider: str | None = None) -> ClosableDocumentStorage:
    """Create the configured local-volume or S3 source-object provider."""

    selected_provider = (provider or settings.document_storage_provider).strip().lower()
    if selected_provider == "local":
        return LocalDocumentStorage(settings.document_storage_root)
    if selected_provider == "s3":
        return S3DocumentStorage()
    raise ValueError(
        f"Unsupported document storage provider: {selected_provider}. Expected 'local' or 's3'."
    )
