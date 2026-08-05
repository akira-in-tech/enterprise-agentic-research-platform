import re
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import KnowledgeDocument

SUPPORTED_DOCUMENT_MEDIA_TYPES = frozenset(
    {
        "application/pdf",
        "text/markdown",
        "text/plain",
    }
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class KnowledgeDocumentTransitionError(RuntimeError):
    """Indicate that a document lifecycle transition was rejected."""


def _normalize_required(
    value: str,
    *,
    field_name: str,
    max_length: int,
) -> str:
    normalized = value.strip()

    if not normalized:
        raise ValueError(f"{field_name} must not be empty.")

    if len(normalized) > max_length:
        raise ValueError(f"{field_name} must not exceed {max_length} characters.")

    return normalized


class KnowledgeDocumentRepository:
    """Persist and query tenant-scoped private-knowledge documents."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        filename: str,
        media_type: str,
        byte_size: int,
        content_sha256: str,
        storage_key: str,
        uploaded_by_user_id: UUID | None = None,
    ) -> KnowledgeDocument:
        """Create a pending document without committing its transaction."""

        normalized_media_type = media_type.strip().lower()
        normalized_sha256 = content_sha256.strip().lower()

        if normalized_media_type not in SUPPORTED_DOCUMENT_MEDIA_TYPES:
            raise ValueError(
                "media_type must be 'application/pdf', 'text/markdown', or 'text/plain'."
            )

        if byte_size <= 0:
            raise ValueError("byte_size must be greater than zero.")

        if SHA256_PATTERN.fullmatch(normalized_sha256) is None:
            raise ValueError("content_sha256 must be a lowercase 64-character SHA-256 digest.")

        document = KnowledgeDocument(
            tenant_id=tenant_id,
            uploaded_by_user_id=uploaded_by_user_id,
            filename=_normalize_required(
                filename,
                field_name="filename",
                max_length=255,
            ),
            media_type=normalized_media_type,
            byte_size=byte_size,
            content_sha256=normalized_sha256,
            storage_key=_normalize_required(
                storage_key,
                field_name="storage_key",
                max_length=1024,
            ),
            status="pending",
        )
        self._session.add(document)
        await self._session.flush()

        return document

    async def get_for_tenant(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> KnowledgeDocument | None:
        """Return a document only when it belongs to the tenant."""

        result = await self._session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.tenant_id == tenant_id,
                KnowledgeDocument.id == document_id,
            )
        )

        return result

    async def list_for_tenant(
        self,
        *,
        tenant_id: UUID,
        limit: int = 50,
    ) -> list[KnowledgeDocument]:
        """Return recent tenant documents in deterministic order."""

        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100.")

        result = await self._session.scalars(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.tenant_id == tenant_id)
            .order_by(
                KnowledgeDocument.created_at.desc(),
                KnowledgeDocument.id.desc(),
            )
            .limit(limit)
        )

        return list(result)

    async def mark_indexing(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> KnowledgeDocument:
        """Atomically move a pending or failed document into indexing."""

        return await self._transition(
            tenant_id=tenant_id,
            document_id=document_id,
            from_statuses=("pending", "failed"),
            values={
                "status": "indexing",
                "error_message": None,
                "indexed_at": None,
                "updated_at": func.now(),
            },
            target_status="indexing",
        )

    async def mark_ready(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> KnowledgeDocument:
        """Atomically mark an indexed document ready for retrieval."""

        return await self._transition(
            tenant_id=tenant_id,
            document_id=document_id,
            from_statuses=("indexing",),
            values={
                "status": "ready",
                "error_message": None,
                "indexed_at": func.now(),
                "updated_at": func.now(),
            },
            target_status="ready",
        )

    async def mark_failed(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
        error_message: str,
    ) -> KnowledgeDocument:
        """Atomically record a bounded indexing failure message."""

        normalized_error = _normalize_required(
            error_message,
            field_name="error_message",
            max_length=4_000,
        )

        return await self._transition(
            tenant_id=tenant_id,
            document_id=document_id,
            from_statuses=("pending", "indexing"),
            values={
                "status": "failed",
                "error_message": normalized_error,
                "indexed_at": None,
                "updated_at": func.now(),
            },
            target_status="failed",
        )

    async def mark_deleting(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> KnowledgeDocument:
        """Atomically reserve one document for external-resource cleanup."""

        return await self._transition(
            tenant_id=tenant_id,
            document_id=document_id,
            from_statuses=("pending", "indexing", "ready", "failed"),
            values={
                "status": "deleting",
                "error_message": None,
                "indexed_at": None,
                "updated_at": func.now(),
            },
            target_status="deleting",
        )

    async def delete_marked(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> KnowledgeDocument:
        """Delete a row only after it entered the deleting state."""

        result = await self._session.scalar(
            delete(KnowledgeDocument)
            .where(
                KnowledgeDocument.tenant_id == tenant_id,
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.status == "deleting",
            )
            .returning(KnowledgeDocument)
        )

        if result is None:
            raise KnowledgeDocumentTransitionError(
                "Knowledge document is missing or cannot be deleted."
            )

        return result

    async def _transition(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
        from_statuses: tuple[str, ...],
        values: dict[str, object],
        target_status: str,
    ) -> KnowledgeDocument:
        result = await self._session.scalar(
            update(KnowledgeDocument)
            .where(
                KnowledgeDocument.tenant_id == tenant_id,
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.status.in_(from_statuses),
            )
            .values(**values)
            .returning(KnowledgeDocument)
        )

        if result is None:
            raise KnowledgeDocumentTransitionError(
                f"Knowledge document is missing or cannot transition to {target_status}."
            )

        return result
