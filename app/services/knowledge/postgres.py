from collections.abc import Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import KnowledgeDocumentRepository
from app.schemas.knowledge import KnowledgeDocumentRecord
from app.services.research.postgres import TransactionalSessionFactory

DocumentRepositoryFactory = Callable[[AsyncSession], KnowledgeDocumentRepository]


class PostgresKnowledgeDocumentStore:
    """Persist document lifecycle changes using short transactions."""

    def __init__(
        self,
        session_factory: TransactionalSessionFactory,
        repository_factory: DocumentRepositoryFactory = KnowledgeDocumentRepository,
    ) -> None:
        self._session_factory = session_factory
        self._repository_factory = repository_factory

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
    ) -> KnowledgeDocumentRecord:
        """Commit one validated pending document."""

        async with self._session_factory.begin() as session:
            repository = self._repository_factory(session)
            document = await repository.create(
                document_id=document_id,
                tenant_id=tenant_id,
                uploaded_by_user_id=uploaded_by_user_id,
                filename=filename,
                media_type=media_type,
                byte_size=byte_size,
                content_sha256=content_sha256,
                vector_document_id=vector_document_id,
                storage_key=storage_key,
            )
            return KnowledgeDocumentRecord.model_validate(document)

    async def get(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> KnowledgeDocumentRecord | None:
        """Return one document only within its tenant boundary."""

        async with self._session_factory.begin() as session:
            document = await self._repository_factory(session).get_for_tenant(
                tenant_id=tenant_id,
                document_id=document_id,
            )
            return (
                KnowledgeDocumentRecord.model_validate(document) if document is not None else None
            )

    async def find_by_content_sha256(
        self,
        *,
        tenant_id: UUID,
        content_sha256: str,
    ) -> KnowledgeDocumentRecord | None:
        """Find duplicate normalized content only inside one tenant."""

        async with self._session_factory.begin() as session:
            document = await self._repository_factory(session).get_by_content_sha256(
                tenant_id=tenant_id,
                content_sha256=content_sha256,
            )
            return (
                KnowledgeDocumentRecord.model_validate(document) if document is not None else None
            )

    async def list(
        self,
        *,
        tenant_id: UUID,
        limit: int,
    ) -> list[KnowledgeDocumentRecord]:
        """Return recent tenant documents."""

        async with self._session_factory.begin() as session:
            documents = await self._repository_factory(session).list_for_tenant(
                tenant_id=tenant_id,
                limit=limit,
            )
            return [KnowledgeDocumentRecord.model_validate(document) for document in documents]

    async def mark_indexing(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> KnowledgeDocumentRecord:
        """Commit the transition into indexing."""

        return await self._transition(
            tenant_id=tenant_id,
            document_id=document_id,
            method_name="mark_indexing",
        )

    async def mark_ready(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> KnowledgeDocumentRecord:
        """Commit the transition into ready."""

        return await self._transition(
            tenant_id=tenant_id,
            document_id=document_id,
            method_name="mark_ready",
        )

    async def mark_deleting(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> KnowledgeDocumentRecord:
        """Commit the transition into deleting."""

        return await self._transition(
            tenant_id=tenant_id,
            document_id=document_id,
            method_name="mark_deleting",
        )

    async def mark_failed(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
        error_message: str,
    ) -> KnowledgeDocumentRecord:
        """Commit a document operation failure."""

        async with self._session_factory.begin() as session:
            document = await self._repository_factory(session).mark_failed(
                tenant_id=tenant_id,
                document_id=document_id,
                error_message=error_message,
            )
            return KnowledgeDocumentRecord.model_validate(document)

    async def delete_marked(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> None:
        """Commit deletion after external cleanup succeeds."""

        async with self._session_factory.begin() as session:
            await self._repository_factory(session).delete_marked(
                tenant_id=tenant_id,
                document_id=document_id,
            )

    async def _transition(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
        method_name: str,
    ) -> KnowledgeDocumentRecord:
        async with self._session_factory.begin() as session:
            repository = self._repository_factory(session)
            method = getattr(repository, method_name)
            document = await method(
                tenant_id=tenant_id,
                document_id=document_id,
            )
            return KnowledgeDocumentRecord.model_validate(document)
