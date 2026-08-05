from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from httpx import Response

from app.api.dependencies import get_knowledge_document_service
from app.main import app
from app.schemas.knowledge import KnowledgeDocumentResponse
from app.services.knowledge import (
    KnowledgeDocumentAlreadyExistsError,
    KnowledgeDocumentIndexingError,
)


def create_response(
    *,
    tenant_id: UUID,
    document_id: UUID | None = None,
) -> KnowledgeDocumentResponse:
    now = datetime.now(UTC)
    return KnowledgeDocumentResponse(
        id=document_id or uuid4(),
        tenant_id=tenant_id,
        uploaded_by_user_id=None,
        filename="architecture.md",
        media_type="text/markdown",
        byte_size=16,
        content_sha256="a" * 64,
        status="ready",
        error_message=None,
        created_at=now,
        updated_at=now,
        indexed_at=now,
    )


class FakeKnowledgeDocumentService:
    max_upload_bytes = 100

    def __init__(
        self,
        *,
        response: KnowledgeDocumentResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def upload(self, **values: object) -> KnowledgeDocumentResponse:
        self.calls.append(values)
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response

    async def list(self, *, tenant_id: UUID, limit: int) -> list[KnowledgeDocumentResponse]:
        self.calls.append({"tenant_id": tenant_id, "limit": limit})
        return [self.response] if self.response is not None else []

    async def get(self, *, tenant_id: UUID, document_id: UUID) -> KnowledgeDocumentResponse | None:
        self.calls.append({"tenant_id": tenant_id, "document_id": document_id})
        return self.response

    async def delete(self, *, tenant_id: UUID, document_id: UUID) -> bool:
        self.calls.append({"tenant_id": tenant_id, "document_id": document_id})
        return self.response is not None


def request_with_service(
    service: FakeKnowledgeDocumentService,
    method: str,
    path: str,
    **kwargs: Any,
) -> Response:
    app.dependency_overrides[get_knowledge_document_service] = lambda: service
    try:
        with TestClient(app) as client:
            return cast(Response, client.request(method, path, **kwargs))
    finally:
        app.dependency_overrides.clear()


def test_upload_document_passes_tenant_user_and_multipart_content() -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    document = create_response(tenant_id=tenant_id)
    service = FakeKnowledgeDocumentService(response=document)

    response = request_with_service(
        service,
        "POST",
        "/documents",
        headers={"X-Tenant-ID": str(tenant_id), "X-User-ID": str(user_id)},
        files={"file": ("architecture.md", b"trusted evidence", "text/markdown")},
    )

    assert response.status_code == 201
    assert response.json()["id"] == str(document.id)
    assert service.calls == [
        {
            "tenant_id": tenant_id,
            "uploaded_by_user_id": user_id,
            "filename": "architecture.md",
            "declared_media_type": "text/markdown",
            "raw_content": b"trusted evidence",
        }
    ]


def test_upload_document_rejects_oversized_body_before_service_call() -> None:
    service = FakeKnowledgeDocumentService()

    response = request_with_service(
        service,
        "POST",
        "/documents",
        headers={"X-Tenant-ID": str(uuid4())},
        files={"file": ("large.txt", b"x" * 101, "text/plain")},
    )

    assert response.status_code == 413
    assert service.calls == []


def test_upload_document_maps_duplicate_to_conflict() -> None:
    service = FakeKnowledgeDocumentService(
        error=KnowledgeDocumentAlreadyExistsError("Duplicate content."),
    )

    response = request_with_service(
        service,
        "POST",
        "/documents",
        headers={"X-Tenant-ID": str(uuid4())},
        files={"file": ("architecture.txt", b"trusted evidence", "text/plain")},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Duplicate content."}


def test_upload_document_maps_index_failure_without_claiming_success() -> None:
    document_id = uuid4()
    service = FakeKnowledgeDocumentService(
        error=KnowledgeDocumentIndexingError(document_id),
    )

    response = request_with_service(
        service,
        "POST",
        "/documents",
        headers={"X-Tenant-ID": str(uuid4())},
        files={"file": ("architecture.txt", b"trusted evidence", "text/plain")},
    )

    assert response.status_code == 502
    assert str(document_id) in response.json()["detail"]


def test_list_documents_is_tenant_scoped_and_bounded() -> None:
    tenant_id = uuid4()
    document = create_response(tenant_id=tenant_id)
    service = FakeKnowledgeDocumentService(response=document)

    response = request_with_service(
        service,
        "GET",
        "/documents?limit=25",
        headers={"X-Tenant-ID": str(tenant_id)},
    )

    assert response.status_code == 200
    assert response.json()[0]["tenant_id"] == str(tenant_id)
    assert service.calls == [{"tenant_id": tenant_id, "limit": 25}]


def test_get_document_returns_not_found_inside_tenant_boundary() -> None:
    service = FakeKnowledgeDocumentService()

    response = request_with_service(
        service,
        "GET",
        f"/documents/{uuid4()}",
        headers={"X-Tenant-ID": str(uuid4())},
    )

    assert response.status_code == 404


def test_delete_document_returns_no_content() -> None:
    tenant_id = uuid4()
    document_id = uuid4()
    service = FakeKnowledgeDocumentService(
        response=create_response(tenant_id=tenant_id, document_id=document_id),
    )

    response = request_with_service(
        service,
        "DELETE",
        f"/documents/{document_id}",
        headers={"X-Tenant-ID": str(tenant_id)},
    )

    assert response.status_code == 204
    assert response.content == b""
