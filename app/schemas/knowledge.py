from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.document import DocumentMediaType

KnowledgeDocumentStatus = Literal[
    "pending",
    "indexing",
    "ready",
    "failed",
    "deleting",
]


class KnowledgeDocumentResponse(BaseModel):
    """Represent safe tenant-scoped document metadata returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    uploaded_by_user_id: UUID | None
    filename: str
    media_type: DocumentMediaType
    byte_size: int
    content_sha256: str
    status: KnowledgeDocumentStatus
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    indexed_at: datetime | None


class KnowledgeDocumentRecord(KnowledgeDocumentResponse):
    """Represent internal metadata required for storage and vector cleanup."""

    vector_document_id: str | None
    storage_key: str
