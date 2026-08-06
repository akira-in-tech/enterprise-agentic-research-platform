from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest

from app.schemas.document import PrivateDocument
from app.schemas.knowledge import KnowledgeDocumentRecord, KnowledgeDocumentStatus
from app.services.knowledge import (
    KnowledgeDocumentAlreadyExistsError,
    KnowledgeDocumentIndexingError,
    KnowledgeDocumentService,
)
from app.services.knowledge.indexing import KnowledgeIndexer
from app.services.knowledge.management import KnowledgeDocumentStore
from app.services.storage import DocumentStorage
from app.services.vector_store.base import VectorStore


def create_record(
    *,
    tenant_id: UUID,
    document_id: UUID,
    status: str,
    vector_document_id: str = "DOC-0123456789ABCDEF",
    error_message: str | None = None,
) -> KnowledgeDocumentRecord:
    now = datetime.now(UTC)
    return KnowledgeDocumentRecord(
        id=document_id,
        tenant_id=tenant_id,
        uploaded_by_user_id=None,
        filename="architecture.md",
        media_type="text/markdown",
        byte_size=16,
        content_sha256="a" * 64,
        vector_document_id=vector_document_id,
        storage_key=f"tenants/{tenant_id}/documents/{document_id}/source.md",
        status=cast(KnowledgeDocumentStatus, status),
        error_message=error_message,
        created_at=now,
        updated_at=now,
        indexed_at=now if status == "ready" else None,
    )


class RecordingStore:
    def __init__(self, *, duplicate: KnowledgeDocumentRecord | None = None) -> None:
        self.duplicate = duplicate
        self.record: KnowledgeDocumentRecord | None = None
        self.events: list[str] = []

    async def find_by_content_sha256(
        self, *, tenant_id: UUID, content_sha256: str
    ) -> KnowledgeDocumentRecord | None:
        self.events.append("find")
        return self.duplicate

    async def create_pending(self, **values: object) -> KnowledgeDocumentRecord:
        self.events.append("create")
        tenant_id = cast(UUID, values["tenant_id"])
        document_id = cast(UUID, values["document_id"])
        self.record = create_record(
            tenant_id=tenant_id,
            document_id=document_id,
            status="pending",
            vector_document_id=cast(str, values["vector_document_id"]),
        )
        return self.record

    async def get(self, *, tenant_id: UUID, document_id: UUID) -> KnowledgeDocumentRecord | None:
        self.events.append("get")
        if self.record is None or self.record.tenant_id != tenant_id:
            return None
        return self.record

    async def list(self, *, tenant_id: UUID, limit: int) -> list[KnowledgeDocumentRecord]:
        self.events.append("list")
        return [self.record] if self.record is not None else []

    async def mark_indexing(self, *, tenant_id: UUID, document_id: UUID) -> KnowledgeDocumentRecord:
        return self._transition("indexing", tenant_id, document_id)

    async def mark_ready(self, *, tenant_id: UUID, document_id: UUID) -> KnowledgeDocumentRecord:
        return self._transition("ready", tenant_id, document_id)

    async def mark_failed(
        self, *, tenant_id: UUID, document_id: UUID, error_message: str
    ) -> KnowledgeDocumentRecord:
        return self._transition("failed", tenant_id, document_id, error_message)

    async def mark_deleting(self, *, tenant_id: UUID, document_id: UUID) -> KnowledgeDocumentRecord:
        return self._transition("deleting", tenant_id, document_id)

    async def delete_marked(self, *, tenant_id: UUID, document_id: UUID) -> None:
        self.events.append("delete-metadata")
        self.record = None

    def _transition(
        self,
        status: str,
        tenant_id: UUID,
        document_id: UUID,
        error_message: str | None = None,
    ) -> KnowledgeDocumentRecord:
        self.events.append(status)
        assert self.record is not None
        self.record = create_record(
            tenant_id=tenant_id,
            document_id=document_id,
            status=status,
            vector_document_id=self.record.vector_document_id or "DOC-0123456789ABCDEF",
            error_message=error_message,
        )
        return self.record


class RecordingStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.events: list[str] = []

    async def put(self, *, key: str, content: bytes) -> None:
        self.events.append("put")
        self.objects[key] = content

    async def get(self, *, key: str) -> bytes:
        return self.objects[key]

    async def delete(self, *, key: str) -> None:
        self.events.append("delete-source")
        self.objects.pop(key, None)


class RecordingIndexer:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.documents: list[PrivateDocument] = []

    async def index_document(self, document: PrivateDocument) -> object:
        self.documents.append(document)
        if self.error is not None:
            raise self.error
        return object()


class RecordingVectorStore:
    dimensions = 3

    def __init__(self) -> None:
        self.deleted: list[tuple[str, str]] = []

    async def delete_document(self, *, tenant_id: str, document_id: str) -> int:
        self.deleted.append((tenant_id, document_id))
        return 1


def create_service(
    store: RecordingStore,
    storage: RecordingStorage,
    indexer: RecordingIndexer,
    vector_store: RecordingVectorStore,
) -> KnowledgeDocumentService:
    return KnowledgeDocumentService(
        cast(KnowledgeDocumentStore, store),
        cast(DocumentStorage, storage),
        cast(KnowledgeIndexer, indexer),
        cast(VectorStore, vector_store),
    )


@pytest.mark.anyio
async def test_upload_persists_source_and_indexes_outside_metadata_transitions() -> None:
    tenant_id = uuid4()
    store = RecordingStore()
    storage = RecordingStorage()
    indexer = RecordingIndexer()
    vector_store = RecordingVectorStore()
    service = create_service(store, storage, indexer, vector_store)

    result = await service.upload(
        tenant_id=tenant_id,
        uploaded_by_user_id=None,
        filename="architecture.md",
        declared_media_type="text/markdown",
        raw_content=b"Evidence before conclusions.",
    )

    assert result.status == "ready"
    assert store.events == ["find", "create", "indexing", "ready"]
    assert storage.events == ["put"]
    assert len(indexer.documents) == 1
    assert indexer.documents[0].tenant_id == str(tenant_id)


@pytest.mark.anyio
async def test_upload_rejects_duplicate_before_writing_source() -> None:
    tenant_id = uuid4()
    duplicate = create_record(
        tenant_id=tenant_id,
        document_id=uuid4(),
        status="ready",
    )
    store = RecordingStore(duplicate=duplicate)
    storage = RecordingStorage()
    service = create_service(store, storage, RecordingIndexer(), RecordingVectorStore())

    with pytest.raises(KnowledgeDocumentAlreadyExistsError):
        await service.upload(
            tenant_id=tenant_id,
            uploaded_by_user_id=None,
            filename="architecture.md",
            declared_media_type="text/markdown",
            raw_content=b"Evidence before conclusions.",
        )

    assert storage.events == []
    assert store.events == ["find"]


@pytest.mark.anyio
async def test_upload_records_failed_status_when_indexing_fails() -> None:
    store = RecordingStore()
    storage = RecordingStorage()
    service = create_service(
        store,
        storage,
        RecordingIndexer(error=RuntimeError("embedding unavailable")),
        RecordingVectorStore(),
    )

    with pytest.raises(KnowledgeDocumentIndexingError):
        await service.upload(
            tenant_id=uuid4(),
            uploaded_by_user_id=None,
            filename="architecture.txt",
            declared_media_type="text/plain",
            raw_content=b"Evidence before conclusions.",
        )

    assert store.events[-1] == "failed"
    assert store.record is not None
    assert store.record.error_message == "Indexing failed: RuntimeError."


@pytest.mark.anyio
async def test_delete_cleans_vectors_source_and_metadata_for_same_tenant() -> None:
    tenant_id = uuid4()
    document_id = uuid4()
    store = RecordingStore()
    store.record = create_record(
        tenant_id=tenant_id,
        document_id=document_id,
        status="ready",
    )
    storage = RecordingStorage()
    vector_store = RecordingVectorStore()
    service = create_service(store, storage, RecordingIndexer(), vector_store)

    assert await service.delete(tenant_id=tenant_id, document_id=document_id) is True
    assert vector_store.deleted == [(str(tenant_id), "DOC-0123456789ABCDEF")]
    assert store.events == ["get", "deleting", "delete-metadata"]
    assert storage.events == ["delete-source"]
    assert store.record is None


@pytest.mark.anyio
async def test_delete_does_not_cross_tenant_boundary() -> None:
    owner_tenant_id = uuid4()
    store = RecordingStore()
    store.record = create_record(
        tenant_id=owner_tenant_id,
        document_id=uuid4(),
        status="ready",
    )
    storage = RecordingStorage()
    vector_store = RecordingVectorStore()
    service = create_service(store, storage, RecordingIndexer(), vector_store)

    assert await service.delete(tenant_id=uuid4(), document_id=store.record.id) is False
    assert storage.events == []
    assert vector_store.deleted == []
