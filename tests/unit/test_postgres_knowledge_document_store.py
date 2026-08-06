from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import KnowledgeDocument
from app.db.repositories import KnowledgeDocumentRepository
from app.services.knowledge.postgres import PostgresKnowledgeDocumentStore


class RecordingSessionFactory:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.begin_calls = 0

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[AsyncSession]:
        self.begin_calls += 1
        yield self.session


def create_dependencies() -> tuple[
    RecordingSessionFactory,
    AsyncMock,
    KnowledgeDocumentRepository,
]:
    session = cast(AsyncSession, AsyncMock(spec=AsyncSession))
    repository_mock = AsyncMock(spec=KnowledgeDocumentRepository)
    return (
        RecordingSessionFactory(session),
        repository_mock,
        cast(KnowledgeDocumentRepository, repository_mock),
    )


def create_document(
    *,
    tenant_id: UUID,
    document_id: UUID,
    status: str,
) -> KnowledgeDocument:
    now = datetime.now(UTC)
    return KnowledgeDocument(
        id=document_id,
        tenant_id=tenant_id,
        uploaded_by_user_id=None,
        filename="architecture.md",
        media_type="text/markdown",
        byte_size=16,
        content_sha256="a" * 64,
        vector_document_id="DOC-0123456789ABCDEF",
        storage_key=f"tenants/{tenant_id}/documents/{document_id}/source.md",
        status=status,
        error_message=None,
        created_at=now,
        updated_at=now,
        indexed_at=now if status == "ready" else None,
    )


@pytest.mark.anyio
async def test_store_creates_pending_metadata_in_one_transaction() -> None:
    session_factory, repository_mock, repository = create_dependencies()
    tenant_id = uuid4()
    document_id = uuid4()
    document = create_document(
        tenant_id=tenant_id,
        document_id=document_id,
        status="pending",
    )
    repository_mock.create.return_value = document
    store = PostgresKnowledgeDocumentStore(session_factory, lambda _: repository)

    result = await store.create_pending(
        document_id=document_id,
        tenant_id=tenant_id,
        uploaded_by_user_id=None,
        filename="architecture.md",
        media_type="text/markdown",
        byte_size=16,
        content_sha256="a" * 64,
        vector_document_id="DOC-0123456789ABCDEF",
        storage_key=document.storage_key,
    )

    assert result.id == document_id
    assert result.vector_document_id == "DOC-0123456789ABCDEF"
    assert session_factory.begin_calls == 1
    repository_mock.create.assert_awaited_once_with(
        document_id=document_id,
        tenant_id=tenant_id,
        uploaded_by_user_id=None,
        filename="architecture.md",
        media_type="text/markdown",
        byte_size=16,
        content_sha256="a" * 64,
        vector_document_id="DOC-0123456789ABCDEF",
        storage_key=document.storage_key,
    )


@pytest.mark.anyio
async def test_store_reads_document_inside_tenant_transaction() -> None:
    session_factory, repository_mock, repository = create_dependencies()
    tenant_id = uuid4()
    document_id = uuid4()
    repository_mock.get_for_tenant.return_value = create_document(
        tenant_id=tenant_id,
        document_id=document_id,
        status="ready",
    )
    store = PostgresKnowledgeDocumentStore(session_factory, lambda _: repository)

    result = await store.get(tenant_id=tenant_id, document_id=document_id)

    assert result is not None
    assert result.status == "ready"
    assert session_factory.begin_calls == 1
    repository_mock.get_for_tenant.assert_awaited_once_with(
        tenant_id=tenant_id,
        document_id=document_id,
    )


@pytest.mark.parametrize(
    ("method_name", "repository_method", "status"),
    [
        ("mark_indexing", "mark_indexing", "indexing"),
        ("mark_ready", "mark_ready", "ready"),
        ("mark_deleting", "mark_deleting", "deleting"),
    ],
)
@pytest.mark.anyio
async def test_store_commits_each_lifecycle_transition(
    method_name: str,
    repository_method: str,
    status: str,
) -> None:
    session_factory, repository_mock, repository = create_dependencies()
    tenant_id = uuid4()
    document_id = uuid4()
    getattr(repository_mock, repository_method).return_value = create_document(
        tenant_id=tenant_id,
        document_id=document_id,
        status=status,
    )
    store = PostgresKnowledgeDocumentStore(session_factory, lambda _: repository)

    result = await getattr(store, method_name)(
        tenant_id=tenant_id,
        document_id=document_id,
    )

    assert result.status == status
    assert session_factory.begin_calls == 1
    getattr(repository_mock, repository_method).assert_awaited_once_with(
        tenant_id=tenant_id,
        document_id=document_id,
    )


@pytest.mark.anyio
async def test_store_deletes_only_after_external_cleanup_transition() -> None:
    session_factory, repository_mock, repository = create_dependencies()
    tenant_id = uuid4()
    document_id = uuid4()
    store = PostgresKnowledgeDocumentStore(session_factory, lambda _: repository)

    await store.delete_marked(tenant_id=tenant_id, document_id=document_id)

    assert session_factory.begin_calls == 1
    repository_mock.delete_marked.assert_awaited_once_with(
        tenant_id=tenant_id,
        document_id=document_id,
    )
