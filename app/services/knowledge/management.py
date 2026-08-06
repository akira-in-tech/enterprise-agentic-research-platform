from collections.abc import Sequence
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.schemas.document import PrivateDocument
from app.schemas.knowledge import KnowledgeDocumentRecord, KnowledgeDocumentResponse
from app.services.knowledge.documents import create_text_document
from app.services.knowledge.indexing import KnowledgeIndexer
from app.services.knowledge.pdfs import create_pdf_document
from app.services.storage import DocumentStorage
from app.services.vector_store.base import VectorStore


class KnowledgeDocumentStore(Protocol):
    """Define durable document metadata operations used by the service."""

    async def create_pending(
        self,
        *,
        document_id: UUID,
        tenant_id: UUID,
        uploaded_by_user_id: UUID | None,
        filename: str,
        media_type: str,
        byte_size: int,
        content_sha256: str,
        vector_document_id: str,
        storage_key: str,
    ) -> KnowledgeDocumentRecord: ...

    async def get(
        self, *, tenant_id: UUID, document_id: UUID
    ) -> KnowledgeDocumentRecord | None: ...

    async def find_by_content_sha256(
        self, *, tenant_id: UUID, content_sha256: str
    ) -> KnowledgeDocumentRecord | None: ...

    async def list(self, *, tenant_id: UUID, limit: int) -> list[KnowledgeDocumentRecord]: ...

    async def mark_indexing(
        self, *, tenant_id: UUID, document_id: UUID
    ) -> KnowledgeDocumentRecord: ...

    async def mark_ready(
        self, *, tenant_id: UUID, document_id: UUID
    ) -> KnowledgeDocumentRecord: ...

    async def mark_failed(
        self, *, tenant_id: UUID, document_id: UUID, error_message: str
    ) -> KnowledgeDocumentRecord: ...

    async def mark_deleting(
        self, *, tenant_id: UUID, document_id: UUID
    ) -> KnowledgeDocumentRecord: ...

    async def delete_marked(self, *, tenant_id: UUID, document_id: UUID) -> None: ...


class KnowledgeDocumentAlreadyExistsError(RuntimeError):
    """Indicate duplicate normalized content within one tenant."""


class KnowledgeDocumentIndexingError(RuntimeError):
    """Indicate that a persisted document could not be indexed."""

    def __init__(self, document_id: UUID) -> None:
        super().__init__(f"Private document {document_id} could not be indexed.")
        self.document_id = document_id


class KnowledgeDocumentDeletionError(RuntimeError):
    """Indicate that external document cleanup did not complete."""


class KnowledgeDocumentNotFoundError(RuntimeError):
    """Indicate a document ID that does not belong to this tenant."""

    def __init__(self, document_id: UUID) -> None:
        super().__init__(f"Private document {document_id} was not found.")
        self.document_id = document_id


class KnowledgeDocumentNotReadyError(RuntimeError):
    """Indicate a document that has not finished indexing yet."""

    def __init__(self, document_id: UUID) -> None:
        super().__init__(f"Private document {document_id} has not finished indexing.")
        self.document_id = document_id


class KnowledgeDocumentService:
    """Coordinate validated source storage, indexing, metadata, and deletion."""

    def __init__(
        self,
        store: KnowledgeDocumentStore,
        storage: DocumentStorage,
        indexer: KnowledgeIndexer,
        vector_store: VectorStore,
        *,
        max_upload_bytes: int = 10_000_000,
    ) -> None:
        if max_upload_bytes < 1:
            raise ValueError("max_upload_bytes must be greater than zero.")

        self._store = store
        self._storage = storage
        self._indexer = indexer
        self._vector_store = vector_store
        self._max_upload_bytes = max_upload_bytes

    @property
    def max_upload_bytes(self) -> int:
        """Return the bounded request-body size used by the API."""

        return self._max_upload_bytes

    async def upload(
        self,
        *,
        tenant_id: UUID,
        uploaded_by_user_id: UUID | None,
        filename: str,
        declared_media_type: str | None,
        raw_content: bytes,
    ) -> KnowledgeDocumentResponse:
        """Store, persist, and index one validated private document."""

        document = self._parse_document(
            tenant_id=tenant_id,
            filename=filename,
            declared_media_type=declared_media_type,
            raw_content=raw_content,
        )
        duplicate = await self._store.find_by_content_sha256(
            tenant_id=tenant_id,
            content_sha256=document.content_sha256,
        )

        if duplicate is not None:
            raise KnowledgeDocumentAlreadyExistsError(
                f"Private document content already exists as {duplicate.id}."
            )

        document_id = uuid4()
        suffix = Path(document.filename).suffix.casefold()
        storage_key = f"tenants/{tenant_id}/documents/{document_id}/source{suffix}"

        await self._storage.put(
            key=storage_key,
            content=raw_content,
        )

        try:
            await self._store.create_pending(
                document_id=document_id,
                tenant_id=tenant_id,
                uploaded_by_user_id=uploaded_by_user_id,
                filename=document.filename,
                media_type=document.media_type,
                byte_size=len(raw_content),
                content_sha256=document.content_sha256,
                vector_document_id=document.document_id,
                storage_key=storage_key,
            )
        except IntegrityError as error:
            await self._storage.delete(key=storage_key)
            raise KnowledgeDocumentAlreadyExistsError(
                "Private document content already exists for this tenant."
            ) from error
        except Exception:
            await self._storage.delete(key=storage_key)
            raise

        await self._store.mark_indexing(
            tenant_id=tenant_id,
            document_id=document_id,
        )

        try:
            await self._indexer.index_document(document)
        except Exception as error:
            await self._mark_failed(
                tenant_id=tenant_id,
                document_id=document_id,
                message=f"Indexing failed: {type(error).__name__}.",
            )
            raise KnowledgeDocumentIndexingError(document_id) from error

        ready = await self._store.mark_ready(
            tenant_id=tenant_id,
            document_id=document_id,
        )
        return self._public_response(ready)

    async def get(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> KnowledgeDocumentResponse | None:
        """Return one tenant document."""

        document = await self._store.get(
            tenant_id=tenant_id,
            document_id=document_id,
        )
        return self._public_response(document) if document is not None else None

    async def resolve_vector_document_ids(
        self,
        *,
        tenant_id: UUID,
        document_ids: Sequence[UUID],
    ) -> list[str]:
        """Translate durable document IDs into vector-store document IDs.

        Every ID must belong to this tenant and have finished indexing, so a
        research request can never be scoped to a document it can't actually
        search.
        """

        vector_document_ids: list[str] = []

        for document_id in document_ids:
            document = await self._store.get(
                tenant_id=tenant_id,
                document_id=document_id,
            )

            if document is None:
                raise KnowledgeDocumentNotFoundError(document_id)

            if document.status != "ready" or document.vector_document_id is None:
                raise KnowledgeDocumentNotReadyError(document_id)

            vector_document_ids.append(document.vector_document_id)

        return vector_document_ids

    async def list(
        self,
        *,
        tenant_id: UUID,
        limit: int,
    ) -> list[KnowledgeDocumentResponse]:
        """Return recent tenant documents."""

        documents = await self._store.list(
            tenant_id=tenant_id,
            limit=limit,
        )
        return [self._public_response(document) for document in documents]

    async def delete(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> bool:
        """Delete vectors, the source object, and metadata in recoverable order."""

        existing = await self._store.get(
            tenant_id=tenant_id,
            document_id=document_id,
        )

        if existing is None:
            return False

        deleting = await self._store.mark_deleting(
            tenant_id=tenant_id,
            document_id=document_id,
        )

        try:
            if existing.vector_document_id is not None:
                await self._vector_store.delete_document(
                    tenant_id=str(tenant_id),
                    document_id=existing.vector_document_id,
                )
            await self._storage.delete(key=existing.storage_key)
            await self._store.delete_marked(
                tenant_id=tenant_id,
                document_id=deleting.id,
            )
        except Exception as error:
            await self._mark_failed(
                tenant_id=tenant_id,
                document_id=document_id,
                message=f"Deletion failed: {type(error).__name__}.",
            )
            raise KnowledgeDocumentDeletionError(
                f"Private document {document_id} could not be deleted."
            ) from error

        return True

    def _parse_document(
        self,
        *,
        tenant_id: UUID,
        filename: str,
        declared_media_type: str | None,
        raw_content: bytes,
    ) -> PrivateDocument:
        if not raw_content:
            raise ValueError("Document content must not be empty.")

        if len(raw_content) > self._max_upload_bytes:
            raise ValueError("Document exceeds the maximum allowed size.")

        suffix = Path(filename.strip()).suffix.casefold()

        if suffix == ".pdf":
            document = create_pdf_document(
                tenant_id=str(tenant_id),
                filename=filename,
                raw_content=raw_content,
                max_bytes=self._max_upload_bytes,
            )
        else:
            document = create_text_document(
                tenant_id=str(tenant_id),
                filename=filename,
                raw_content=raw_content,
                max_bytes=self._max_upload_bytes,
            )

        normalized_declared_type = (declared_media_type or "").split(";", 1)[0].strip().lower()
        accepted_declared_types = {document.media_type}

        if document.media_type == "text/markdown":
            accepted_declared_types.add("text/plain")

        if normalized_declared_type and normalized_declared_type not in accepted_declared_types:
            raise ValueError("Declared media type does not match the document extension.")

        return document

    async def _mark_failed(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
        message: str,
    ) -> None:
        try:
            await self._store.mark_failed(
                tenant_id=tenant_id,
                document_id=document_id,
                error_message=message,
            )
        except Exception:
            return

    @staticmethod
    def _public_response(document: KnowledgeDocumentRecord) -> KnowledgeDocumentResponse:
        return KnowledgeDocumentResponse.model_validate(document.model_dump())
