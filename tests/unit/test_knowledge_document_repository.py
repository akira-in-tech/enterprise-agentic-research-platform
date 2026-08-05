from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import KnowledgeDocument
from app.db.repositories import (
    KnowledgeDocumentRepository,
    KnowledgeDocumentTransitionError,
)


def create_session_mock() -> tuple[AsyncSession, AsyncMock]:
    session_mock = AsyncMock(spec=AsyncSession)
    return cast(AsyncSession, session_mock), session_mock


def create_document(*, status: str) -> KnowledgeDocument:
    return KnowledgeDocument(
        id=uuid4(),
        tenant_id=uuid4(),
        filename="architecture.pdf",
        media_type="application/pdf",
        byte_size=1024,
        content_sha256="a" * 64,
        storage_key="tenants/example/documents/architecture.pdf",
        status=status,
        error_message="Indexing failed." if status == "failed" else None,
    )


@pytest.mark.anyio
async def test_repository_creates_normalized_pending_document_without_commit() -> None:
    session, session_mock = create_session_mock()
    repository = KnowledgeDocumentRepository(session)
    tenant_id = uuid4()
    user_id = uuid4()

    document = await repository.create(
        tenant_id=tenant_id,
        uploaded_by_user_id=user_id,
        filename="  architecture.pdf  ",
        media_type="  APPLICATION/PDF  ",
        byte_size=1024,
        content_sha256="A" * 64,
        vector_document_id="doc-0123456789abcdef",
        storage_key="  tenants/example/documents/architecture.pdf  ",
    )

    assert document.tenant_id == tenant_id
    assert document.uploaded_by_user_id == user_id
    assert document.filename == "architecture.pdf"
    assert document.media_type == "application/pdf"
    assert document.content_sha256 == "a" * 64
    assert document.vector_document_id == "DOC-0123456789ABCDEF"
    assert document.storage_key == "tenants/example/documents/architecture.pdf"
    assert document.status == "pending"
    session_mock.add.assert_called_once_with(document)
    session_mock.flush.assert_awaited_once_with()
    session_mock.commit.assert_not_awaited()


@pytest.mark.parametrize(
    ("overrides", "expected_error"),
    [
        ({"filename": "   "}, "filename must not be empty"),
        ({"filename": "a" * 256}, "filename must not exceed 255"),
        ({"media_type": "image/png"}, "media_type must be"),
        ({"byte_size": 0}, "byte_size must be greater than zero"),
        ({"content_sha256": "not-a-digest"}, "content_sha256 must be"),
        ({"storage_key": "   "}, "storage_key must not be empty"),
    ],
)
@pytest.mark.anyio
async def test_repository_rejects_invalid_document_metadata(
    overrides: dict[str, object],
    expected_error: str,
) -> None:
    session, session_mock = create_session_mock()
    repository = KnowledgeDocumentRepository(session)
    values: dict[str, object] = {
        "tenant_id": uuid4(),
        "filename": "architecture.pdf",
        "media_type": "application/pdf",
        "byte_size": 1024,
        "content_sha256": "a" * 64,
        "vector_document_id": "DOC-0123456789ABCDEF",
        "storage_key": "tenants/example/documents/architecture.pdf",
    }
    values.update(overrides)

    with pytest.raises(ValueError, match=expected_error):
        await repository.create(**values)  # type: ignore[arg-type]

    session_mock.add.assert_not_called()
    session_mock.flush.assert_not_awaited()


@pytest.mark.parametrize(
    ("method_name", "status"),
    [
        ("mark_indexing", "indexing"),
        ("mark_ready", "ready"),
        ("mark_deleting", "deleting"),
    ],
)
@pytest.mark.anyio
async def test_repository_applies_atomic_document_transitions(
    method_name: str,
    status: str,
) -> None:
    session, session_mock = create_session_mock()
    repository = KnowledgeDocumentRepository(session)
    document = create_document(status=status)
    session_mock.scalar.return_value = document

    result = await getattr(repository, method_name)(
        tenant_id=document.tenant_id,
        document_id=document.id,
    )

    assert result is document
    session_mock.scalar.assert_awaited_once()
    session_mock.commit.assert_not_awaited()


@pytest.mark.anyio
async def test_repository_records_bounded_failure_without_commit() -> None:
    session, session_mock = create_session_mock()
    repository = KnowledgeDocumentRepository(session)
    document = create_document(status="failed")
    session_mock.scalar.return_value = document

    result = await repository.mark_failed(
        tenant_id=document.tenant_id,
        document_id=document.id,
        error_message="  Embedding provider unavailable.  ",
    )

    assert result is document
    session_mock.scalar.assert_awaited_once()
    session_mock.commit.assert_not_awaited()


@pytest.mark.anyio
async def test_repository_rejects_invalid_transition() -> None:
    session, session_mock = create_session_mock()
    repository = KnowledgeDocumentRepository(session)
    session_mock.scalar.return_value = None

    with pytest.raises(
        KnowledgeDocumentTransitionError,
        match="cannot transition to ready",
    ):
        await repository.mark_ready(
            tenant_id=uuid4(),
            document_id=uuid4(),
        )


@pytest.mark.anyio
async def test_repository_deletes_only_marked_document() -> None:
    session, session_mock = create_session_mock()
    repository = KnowledgeDocumentRepository(session)
    document = create_document(status="deleting")
    session_mock.scalar.return_value = document

    result = await repository.delete_marked(
        tenant_id=document.tenant_id,
        document_id=document.id,
    )

    assert result is document
    session_mock.scalar.assert_awaited_once()
    session_mock.commit.assert_not_awaited()


@pytest.mark.anyio
async def test_repository_lists_only_bounded_tenant_documents() -> None:
    session, session_mock = create_session_mock()
    repository = KnowledgeDocumentRepository(session)
    documents = [create_document(status="ready")]
    session_mock.scalars.return_value = documents

    result = await repository.list_for_tenant(
        tenant_id=uuid4(),
        limit=25,
    )

    assert result == documents
    session_mock.scalars.assert_awaited_once()


@pytest.mark.parametrize("limit", [0, 101])
@pytest.mark.anyio
async def test_repository_rejects_invalid_list_limit(limit: int) -> None:
    session, session_mock = create_session_mock()
    repository = KnowledgeDocumentRepository(session)

    with pytest.raises(ValueError, match="limit must be between 1 and 100"):
        await repository.list_for_tenant(
            tenant_id=uuid4(),
            limit=limit,
        )

    session_mock.scalars.assert_not_awaited()
