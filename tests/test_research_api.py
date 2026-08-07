from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_current_session,
    get_knowledge_document_service,
    get_research_execution_service,
    get_research_job_manager,
    get_research_progress_store,
    get_research_rate_limiter,
    get_research_report_export_service,
    get_research_report_store,
    get_research_run_store,
)
from app.db.models import ResearchRun
from app.main import app
from app.schemas.evidence import CitationAudit, ReflectionDecision
from app.schemas.progress import ResearchProgressRecord
from app.schemas.report import ResearchReportResponse, ResearchReportSourceResponse
from app.services.auth import ResolvedSession
from app.services.cache import (
    CacheUnavailableError,
    ResearchRateLimitDecision,
    ResearchRateLimitUnavailableError,
)
from app.services.knowledge import (
    KnowledgeDocumentNotFoundError,
    KnowledgeDocumentNotReadyError,
)
from app.services.research.execution import (
    ResearchExecutionResult,
)
from app.services.research.idempotency import (
    ResearchIdempotencyConflictError,
    ResearchIdempotencyInProgressError,
    ResearchIdempotencyUnavailableError,
)
from app.services.storage import DocumentNotFoundError, DocumentStorageError
from app.workflow.state import ResearchState


class FakeResearchExecutionService:
    def __init__(
        self,
        *,
        idempotency_replayed: bool = False,
        error: Exception | None = None,
        state: ResearchState | None = None,
    ) -> None:
        self.idempotency_replayed = idempotency_replayed
        self.error = error
        self.state = state
        self.calls: list[dict[str, object]] = []

    async def execute(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: str,
        requested_by_user_id: UUID | None = None,
        idempotency_key: str | None = None,
        document_ids: Sequence[str] | None = None,
    ) -> ResearchExecutionResult:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "query": query,
                "llm_provider": llm_provider,
                "requested_by_user_id": requested_by_user_id,
                "idempotency_key": idempotency_key,
                "document_ids": document_ids,
            }
        )
        if self.error is not None:
            raise self.error
        state: ResearchState = self.state or {
            "query": query,
            "route": "direct",
            "route_reason": ("The question can be answered using stable knowledge."),
            "answer": ("epoll is Linux's scalable I/O notification interface."),
            "status": "direct_answer_completed",
        }

        return ResearchExecutionResult(
            research_run_id=uuid4(),
            llm_provider="ollama",
            state=state,
            idempotency_replayed=self.idempotency_replayed,
        )


class FakeResearchRateLimiter:
    def __init__(
        self,
        *,
        decision: ResearchRateLimitDecision | None = None,
        error: ResearchRateLimitUnavailableError | None = None,
    ) -> None:
        self.decision = decision or ResearchRateLimitDecision(
            allowed=True,
            limit=20,
            remaining=19,
            reset_after_seconds=60,
        )
        self.error = error
        self.calls: list[UUID] = []

    async def check(
        self,
        *,
        tenant_id: UUID,
    ) -> ResearchRateLimitDecision:
        self.calls.append(
            tenant_id,
        )

        if self.error is not None:
            raise self.error

        return self.decision


class FakeResearchProgressStore:
    def __init__(
        self,
        *,
        record: ResearchProgressRecord | None = None,
        error: CacheUnavailableError | None = None,
    ) -> None:
        self.record = record
        self.error = error
        self.calls: list[tuple[UUID, UUID]] = []

    async def get(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> ResearchProgressRecord | None:
        self.calls.append((tenant_id, research_run_id))

        if self.error is not None:
            raise self.error

        return self.record


class FakeResearchJobManager:
    def __init__(
        self,
        research_run_id: UUID | None = None,
        *,
        cancel_result: bool = True,
    ) -> None:
        self.research_run_id = research_run_id or uuid4()
        self.cancel_result = cancel_result
        self.calls: list[dict[str, object]] = []
        self.cancel_calls: list[tuple[UUID, UUID]] = []

    async def submit(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: str,
        requested_by_user_id: UUID | None = None,
        document_ids: Sequence[str] | None = None,
    ) -> UUID:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "query": query,
                "llm_provider": llm_provider,
                "requested_by_user_id": requested_by_user_id,
                "document_ids": document_ids,
            }
        )
        return self.research_run_id

    async def cancel(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> bool:
        self.cancel_calls.append((tenant_id, research_run_id))
        return self.cancel_result


class FakeResearchRunStore:
    def __init__(
        self,
        run: ResearchRun | None = None,
        *,
        runs: list[ResearchRun] | None = None,
    ) -> None:
        self.run = run
        self.runs = runs or []
        self.calls: list[tuple[UUID, UUID]] = []
        self.list_calls: list[tuple[UUID, int]] = []

    async def get(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> ResearchRun | None:
        self.calls.append((tenant_id, research_run_id))
        return self.run

    async def list_recent(
        self,
        *,
        tenant_id: UUID,
        limit: int = 20,
    ) -> list[ResearchRun]:
        self.list_calls.append((tenant_id, limit))
        return self.runs


class FakeResearchReportStore:
    def __init__(self, report: ResearchReportResponse | None = None) -> None:
        self.report = report
        self.calls: list[tuple[UUID, UUID]] = []

    async def get(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> ResearchReportResponse | None:
        self.calls.append((tenant_id, research_run_id))
        return self.report

    async def list_sources(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> list[object] | None:
        self.calls.append((tenant_id, research_run_id))
        if self.report is None:
            return None
        return list(self.report.sources)


class FakeResearchReportExportService:
    def __init__(
        self,
        *,
        storage_key: str = "tenants/example/report-exports/example/report-numbered.md",
        content: bytes = b"# Exported report",
        export_error: Exception | None = None,
        retrieve_error: Exception | None = None,
    ) -> None:
        self.storage_key = storage_key
        self.content = content
        self.export_error = export_error
        self.retrieve_error = retrieve_error
        self.export_calls: list[dict[str, object]] = []
        self.retrieve_calls: list[dict[str, object]] = []

    async def export(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        content: bytes,
        format: str = "markdown",
        citation_style: str = "numbered",
    ) -> str:
        self.export_calls.append(
            {
                "tenant_id": tenant_id,
                "research_run_id": research_run_id,
                "content": content,
                "format": format,
                "citation_style": citation_style,
            }
        )
        if self.export_error is not None:
            raise self.export_error
        return self.storage_key

    async def retrieve(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        format: str = "markdown",
        citation_style: str = "numbered",
    ) -> bytes:
        self.retrieve_calls.append(
            {
                "tenant_id": tenant_id,
                "research_run_id": research_run_id,
                "format": format,
                "citation_style": citation_style,
            }
        )
        if self.retrieve_error is not None:
            raise self.retrieve_error
        return self.content


class FakeKnowledgeDocumentService:
    def __init__(
        self,
        *,
        vector_document_ids: list[str] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.vector_document_ids = vector_document_ids or []
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def resolve_vector_document_ids(
        self,
        *,
        tenant_id: UUID,
        document_ids: Sequence[UUID],
    ) -> list[str]:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "document_ids": list(document_ids),
            }
        )
        if self.error is not None:
            raise self.error
        return self.vector_document_ids


def override_current_session(
    *,
    tenant_id: UUID | None = None,
    user_id: UUID | None = None,
) -> UUID:
    """Install a get_current_session override and return the tenant_id used."""

    resolved_tenant_id = tenant_id or uuid4()
    app.dependency_overrides[get_current_session] = lambda: ResolvedSession(
        tenant_id=resolved_tenant_id,
        user_id=user_id or uuid4(),
    )

    return resolved_tenant_id


def test_get_research_progress_is_tenant_scoped() -> None:
    tenant_id = uuid4()
    research_run_id = uuid4()
    record = ResearchProgressRecord(
        research_run_id=research_run_id,
        status="running",
        message="Research workflow is running.",
        updated_at=datetime.now(UTC),
    )
    progress_store = FakeResearchProgressStore(record=record)
    app.dependency_overrides[get_research_progress_store] = lambda: progress_store
    override_current_session(tenant_id=tenant_id)

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/research-runs/{research_run_id}/progress",
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert progress_store.calls == [(tenant_id, research_run_id)]


def test_get_research_progress_returns_not_found() -> None:
    progress_store = FakeResearchProgressStore()
    app.dependency_overrides[get_research_progress_store] = lambda: progress_store
    override_current_session()

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/research-runs/{uuid4()}/progress",
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Research progress was not found."}


def test_get_research_progress_returns_service_unavailable() -> None:
    progress_store = FakeResearchProgressStore(
        error=CacheUnavailableError("Redis is unavailable."),
    )
    app.dependency_overrides[get_research_progress_store] = lambda: progress_store
    override_current_session()

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/research-runs/{uuid4()}/progress",
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"detail": "Research progress is temporarily unavailable."}


def test_progress_events_stream_terminal_tenant_scoped_snapshot() -> None:
    tenant_id = uuid4()
    research_run_id = uuid4()
    record = ResearchProgressRecord(
        research_run_id=research_run_id,
        status="completed",
        message="Research workflow completed.",
        updated_at=datetime.now(UTC),
        workflow_status="research_report_completed",
    )
    progress_store = FakeResearchProgressStore(record=record)
    app.dependency_overrides[get_research_progress_store] = lambda: progress_store
    override_current_session(tenant_id=tenant_id)

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/research-runs/{research_run_id}/events",
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: progress" in response.text
    assert '"status":"completed"' in response.text
    assert progress_store.calls == [(tenant_id, research_run_id)]


def test_get_research_report_is_tenant_scoped() -> None:
    tenant_id = uuid4()
    research_run_id = uuid4()
    report = ResearchReportResponse(
        report_id=uuid4(),
        research_run_id=research_run_id,
        content="Durable report.",
        workflow_status="research_report_completed",
        citation_valid=True,
        citation_coverage=1,
        reflection_status="approved",
        reflection_reasons=[],
        reflection_attempts=1,
        created_at=datetime.now(UTC),
        sources=[],
    )
    report_store = FakeResearchReportStore(report)
    app.dependency_overrides[get_research_report_store] = lambda: report_store
    override_current_session(tenant_id=tenant_id)

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/research-runs/{research_run_id}/report",
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["content"] == "Durable report."
    assert report_store.calls == [(tenant_id, research_run_id)]


def test_get_research_report_returns_not_found() -> None:
    report_store = FakeResearchReportStore()
    app.dependency_overrides[get_research_report_store] = lambda: report_store
    override_current_session()

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/research-runs/{uuid4()}/report",
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Research report was not found."}


def test_export_research_report_is_tenant_scoped() -> None:
    tenant_id = uuid4()
    research_run_id = uuid4()
    report = ResearchReportResponse(
        report_id=uuid4(),
        research_run_id=research_run_id,
        content="Durable report.",
        workflow_status="research_report_completed",
        citation_valid=True,
        citation_coverage=1,
        reflection_status="approved",
        reflection_reasons=[],
        reflection_attempts=1,
        created_at=datetime.now(UTC),
        sources=[],
    )
    report_store = FakeResearchReportStore(report)
    export_service = FakeResearchReportExportService(
        storage_key=f"tenants/{tenant_id}/report-exports/{research_run_id}/report.md",
    )
    app.dependency_overrides[get_research_report_store] = lambda: report_store
    app.dependency_overrides[get_research_report_export_service] = lambda: export_service
    override_current_session(tenant_id=tenant_id)

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/research-runs/{research_run_id}/report/export",
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json() == {
        "storage_key": f"tenants/{tenant_id}/report-exports/{research_run_id}/report.md",
    }
    assert report_store.calls == [(tenant_id, research_run_id)]
    assert export_service.export_calls == [
        {
            "tenant_id": tenant_id,
            "research_run_id": research_run_id,
            "content": b"Durable report.",
            "format": "markdown",
            "citation_style": "numbered",
        }
    ]


def test_export_research_report_rewrites_citations_for_the_requested_style() -> None:
    tenant_id = uuid4()
    research_run_id = uuid4()
    source = ResearchReportSourceResponse(
        source_id="WEB-0123456789ABCDEF",
        origin="web",
        title="HTTP/3 specification",
        locator="https://example.com/http3",
        provider="fixture",
        relevance=0.9,
        content_quality=0.8,
        traceability=1.0,
        overall_score=0.85,
        cited=True,
    )
    report = ResearchReportResponse(
        report_id=uuid4(),
        research_run_id=research_run_id,
        content="# HTTP/3\n\nHTTP/3 reduces latency. [WEB-0123456789ABCDEF]",
        workflow_status="research_report_completed",
        citation_valid=True,
        citation_coverage=1,
        reflection_status="approved",
        reflection_reasons=[],
        reflection_attempts=1,
        created_at=datetime.now(UTC),
        sources=[source],
    )
    report_store = FakeResearchReportStore(report)
    export_service = FakeResearchReportExportService()
    app.dependency_overrides[get_research_report_store] = lambda: report_store
    app.dependency_overrides[get_research_report_export_service] = lambda: export_service
    override_current_session(tenant_id=tenant_id)

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/research-runs/{research_run_id}/report/export",
                params={"citation_style": "footnote"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    [export_call] = export_service.export_calls
    assert export_call["format"] == "markdown"
    assert export_call["citation_style"] == "footnote"
    rendered = export_call["content"]
    assert isinstance(rendered, bytes)
    rendered_text = rendered.decode("utf-8")
    assert "[^1]" in rendered_text
    assert "[HTTP/3 specification](https://example.com/http3)" in rendered_text


def test_export_research_report_renders_pdf_when_requested() -> None:
    tenant_id = uuid4()
    research_run_id = uuid4()
    report = ResearchReportResponse(
        report_id=uuid4(),
        research_run_id=research_run_id,
        content="# HTTP/3\n\nHTTP/3 reduces latency.",
        workflow_status="research_report_completed",
        citation_valid=True,
        citation_coverage=1,
        reflection_status="approved",
        reflection_reasons=[],
        reflection_attempts=1,
        created_at=datetime.now(UTC),
        sources=[],
    )
    report_store = FakeResearchReportStore(report)
    export_service = FakeResearchReportExportService()
    app.dependency_overrides[get_research_report_store] = lambda: report_store
    app.dependency_overrides[get_research_report_export_service] = lambda: export_service
    override_current_session(tenant_id=tenant_id)

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/research-runs/{research_run_id}/report/export",
                params={"format": "pdf"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    [export_call] = export_service.export_calls
    assert export_call["format"] == "pdf"
    rendered = export_call["content"]
    assert isinstance(rendered, bytes)
    assert rendered.startswith(b"%PDF-")


def test_export_research_report_returns_not_found_without_report() -> None:
    report_store = FakeResearchReportStore()
    export_service = FakeResearchReportExportService()
    app.dependency_overrides[get_research_report_store] = lambda: report_store
    app.dependency_overrides[get_research_report_export_service] = lambda: export_service
    override_current_session()

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/research-runs/{uuid4()}/report/export",
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Research report was not found."}
    assert export_service.export_calls == []


def test_export_research_report_returns_service_unavailable() -> None:
    report = ResearchReportResponse(
        report_id=uuid4(),
        research_run_id=uuid4(),
        content="Durable report.",
        workflow_status="research_report_completed",
        citation_valid=True,
        citation_coverage=1,
        reflection_status="approved",
        reflection_reasons=[],
        reflection_attempts=1,
        created_at=datetime.now(UTC),
        sources=[],
    )
    report_store = FakeResearchReportStore(report)
    export_service = FakeResearchReportExportService(
        export_error=DocumentStorageError("Could not store the private document."),
    )
    app.dependency_overrides[get_research_report_store] = lambda: report_store
    app.dependency_overrides[get_research_report_export_service] = lambda: export_service
    override_current_session()

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/research-runs/{uuid4()}/report/export",
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"detail": "Report export storage is temporarily unavailable."}


def test_download_research_report_export_is_tenant_scoped() -> None:
    tenant_id = uuid4()
    research_run_id = uuid4()
    export_service = FakeResearchReportExportService(content=b"# Exported report\n\nBody.")
    app.dependency_overrides[get_research_report_export_service] = lambda: export_service
    override_current_session(tenant_id=tenant_id)

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/research-runs/{research_run_id}/report/export",
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.text == "# Exported report\n\nBody."
    assert response.headers["content-type"].startswith("text/markdown")
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="report-{research_run_id}-numbered.md"'
    )
    assert export_service.retrieve_calls == [
        {
            "tenant_id": tenant_id,
            "research_run_id": research_run_id,
            "format": "markdown",
            "citation_style": "numbered",
        }
    ]


def test_download_research_report_export_supports_pdf_and_footnote_style() -> None:
    tenant_id = uuid4()
    research_run_id = uuid4()
    export_service = FakeResearchReportExportService(content=b"%PDF-1.7 fake pdf bytes")
    app.dependency_overrides[get_research_report_export_service] = lambda: export_service
    override_current_session(tenant_id=tenant_id)

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/research-runs/{research_run_id}/report/export",
                params={"format": "pdf", "citation_style": "footnote"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"%PDF-1.7 fake pdf bytes"
    assert response.headers["content-type"] == "application/pdf"
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="report-{research_run_id}-footnote.pdf"'
    )
    assert export_service.retrieve_calls == [
        {
            "tenant_id": tenant_id,
            "research_run_id": research_run_id,
            "format": "pdf",
            "citation_style": "footnote",
        }
    ]


def test_download_research_report_export_returns_not_found() -> None:
    export_service = FakeResearchReportExportService(
        retrieve_error=DocumentNotFoundError("The private document was not found."),
    )
    app.dependency_overrides[get_research_report_export_service] = lambda: export_service
    override_current_session()

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/research-runs/{uuid4()}/report/export",
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Report export was not found."}


def test_download_research_report_export_returns_service_unavailable() -> None:
    export_service = FakeResearchReportExportService(
        retrieve_error=DocumentStorageError("Could not read the private document."),
    )
    app.dependency_overrides[get_research_report_export_service] = lambda: export_service
    override_current_session()

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/research-runs/{uuid4()}/report/export",
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"detail": "Report export storage is temporarily unavailable."}


def test_list_research_sources_is_tenant_scoped() -> None:
    tenant_id = uuid4()
    research_run_id = uuid4()
    report = ResearchReportResponse(
        report_id=uuid4(),
        research_run_id=research_run_id,
        content="Durable report.",
        workflow_status="research_report_completed",
        citation_valid=True,
        citation_coverage=1,
        reflection_status="approved",
        reflection_reasons=[],
        reflection_attempts=1,
        created_at=datetime.now(UTC),
        sources=[],
    )
    report_store = FakeResearchReportStore(report)
    app.dependency_overrides[get_research_report_store] = lambda: report_store
    override_current_session(tenant_id=tenant_id)
    try:
        with TestClient(app) as client:
            response = client.get(
                f"/research-runs/{research_run_id}/sources",
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == []
    assert report_store.calls == [(tenant_id, research_run_id)]


@pytest.fixture(autouse=True)
def research_rate_limiter() -> Iterator[FakeResearchRateLimiter]:
    limiter = FakeResearchRateLimiter()
    app.dependency_overrides[get_research_rate_limiter] = lambda: limiter

    yield limiter

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def knowledge_document_service() -> Iterator[FakeKnowledgeDocumentService]:
    service = FakeKnowledgeDocumentService()
    app.dependency_overrides[get_knowledge_document_service] = lambda: service

    yield service

    app.dependency_overrides.clear()


def test_create_research_job_returns_durable_delivery_urls(
    research_rate_limiter: FakeResearchRateLimiter,
) -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    research_run_id = uuid4()
    job_manager = FakeResearchJobManager(research_run_id)
    app.dependency_overrides[get_research_job_manager] = lambda: job_manager
    override_current_session(tenant_id=tenant_id, user_id=user_id)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/research-runs/jobs",
                json={
                    "query": "  Compare HTTP/2 and HTTP/3.  ",
                    "llm_provider": "qwen",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json() == {
        "research_run_id": str(research_run_id),
        "status": "queued",
        "progress_url": f"/research-runs/{research_run_id}/progress",
        "events_url": f"/research-runs/{research_run_id}/events",
        "report_url": f"/research-runs/{research_run_id}/report",
    }
    assert job_manager.calls == [
        {
            "tenant_id": tenant_id,
            "query": "Compare HTTP/2 and HTTP/3.",
            "llm_provider": "qwen",
            "requested_by_user_id": user_id,
            "document_ids": None,
        }
    ]
    assert research_rate_limiter.calls == [tenant_id]


def test_create_research_job_resolves_document_ids_before_queuing(
    research_rate_limiter: FakeResearchRateLimiter,
    knowledge_document_service: FakeKnowledgeDocumentService,
) -> None:
    del research_rate_limiter
    tenant_id = uuid4()
    document_id = uuid4()
    job_manager = FakeResearchJobManager()
    app.dependency_overrides[get_research_job_manager] = lambda: job_manager
    knowledge_document_service.vector_document_ids = ["DOC-0000000000000001"]
    override_current_session(tenant_id=tenant_id)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/research-runs/jobs",
                json={
                    "query": "Summarize the onboarding policy.",
                    "llm_provider": "qwen",
                    "document_ids": [str(document_id)],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert knowledge_document_service.calls == [
        {
            "tenant_id": tenant_id,
            "document_ids": [document_id],
        }
    ]
    assert job_manager.calls[0]["document_ids"] == ["DOC-0000000000000001"]


def test_create_research_job_rejects_an_unknown_document(
    knowledge_document_service: FakeKnowledgeDocumentService,
) -> None:
    document_id = uuid4()
    knowledge_document_service.error = KnowledgeDocumentNotFoundError(document_id)
    app.dependency_overrides[get_research_job_manager] = lambda: FakeResearchJobManager()
    override_current_session()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/research-runs/jobs",
                json={
                    "query": "Summarize the onboarding policy.",
                    "llm_provider": "qwen",
                    "document_ids": [str(document_id)],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_create_research_job_rejects_a_document_still_indexing(
    knowledge_document_service: FakeKnowledgeDocumentService,
) -> None:
    document_id = uuid4()
    knowledge_document_service.error = KnowledgeDocumentNotReadyError(document_id)
    app.dependency_overrides[get_research_job_manager] = lambda: FakeResearchJobManager()
    override_current_session()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/research-runs/jobs",
                json={
                    "query": "Summarize the onboarding policy.",
                    "llm_provider": "qwen",
                    "document_ids": [str(document_id)],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_create_research_run_accepts_qwen_selection(
    research_rate_limiter: FakeResearchRateLimiter,
) -> None:
    fake_service = FakeResearchExecutionService()
    tenant_id = uuid4()
    user_id = uuid4()

    app.dependency_overrides[get_research_execution_service] = lambda: fake_service
    override_current_session(tenant_id=tenant_id, user_id=user_id)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/research-runs",
                headers={
                    "Idempotency-Key": "request-123",
                },
                json={
                    "query": "  Explain Linux epoll.  ",
                    "llm_provider": "qwen",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200

    body = response.json()

    assert body["cache_hit"] is False
    assert body["llm_provider"] == "ollama"
    assert body["status"] == "completed"
    assert body["workflow_status"] == ("direct_answer_completed")
    assert body["route"] == "direct"
    assert body["answer"] is not None
    assert body["idempotency_replayed"] is False
    assert response.headers["X-RateLimit-Limit"] == "20"
    assert response.headers["X-RateLimit-Remaining"] == "19"
    assert response.headers["X-RateLimit-Reset"] == "60"
    assert research_rate_limiter.calls == [
        tenant_id,
    ]

    assert fake_service.calls == [
        {
            "tenant_id": tenant_id,
            "query": "Explain Linux epoll.",
            "llm_provider": "qwen",
            "requested_by_user_id": user_id,
            "idempotency_key": "request-123",
            "document_ids": None,
        }
    ]


def test_create_research_run_exposes_report_quality() -> None:
    source_id = "WEB-0123456789ABCDEF"
    fake_service = FakeResearchExecutionService(
        state={
            "query": "Compare HTTP versions.",
            "route": "deep_research",
            "answer": f"HTTP/3 uses QUIC. [{source_id}]",
            "status": "research_report_completed",
            "citation_audit": CitationAudit(
                valid=True,
                cited_source_ids=[source_id],
                unknown_source_ids=[],
                uncited_claims=[],
                coverage_ratio=1,
            ),
            "reflection": ReflectionDecision(
                status="approved",
                reasons=[],
                evidence_count=2,
                average_evidence_score=0.75,
            ),
        }
    )
    app.dependency_overrides[get_research_execution_service] = lambda: fake_service
    override_current_session()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/research-runs",
                json={"query": "Compare HTTP versions.", "llm_provider": "qwen"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["citation_valid"] is True
    assert response.json()["citation_coverage"] == 1.0
    assert response.json()["reflection_status"] == "approved"
    assert response.json()["reflection_reasons"] == []


def test_create_research_run_exposes_idempotency_replay() -> None:
    fake_service = FakeResearchExecutionService(
        idempotency_replayed=True,
    )

    app.dependency_overrides[get_research_execution_service] = lambda: fake_service
    override_current_session()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/research-runs",
                headers={
                    "Idempotency-Key": "request-123",
                },
                json={
                    "query": "What is a mutex?",
                    "llm_provider": "qwen",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["idempotency_replayed"] is True


def test_create_research_run_rejects_invalid_provider() -> None:
    fake_service = FakeResearchExecutionService()

    app.dependency_overrides[get_research_execution_service] = lambda: fake_service
    override_current_session()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/research-runs",
                json={
                    "query": "Explain DNS recursive resolution.",
                    "llm_provider": "openai",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert fake_service.calls == []


def test_create_research_run_requires_authentication() -> None:
    fake_service = FakeResearchExecutionService()

    app.dependency_overrides[get_research_execution_service] = lambda: fake_service

    def _raise_unauthenticated() -> ResolvedSession:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated.")

    app.dependency_overrides[get_current_session] = _raise_unauthenticated

    try:
        with TestClient(app) as client:
            response = client.post(
                "/research-runs",
                json={
                    "query": "Explain DNS recursive resolution.",
                    "llm_provider": "claude",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert fake_service.calls == []


@pytest.mark.parametrize(
    (
        "error",
        "expected_status",
    ),
    [
        (
            ResearchIdempotencyConflictError("Idempotency key conflict."),
            409,
        ),
        (
            ResearchIdempotencyUnavailableError("Idempotency service unavailable."),
            503,
        ),
        (
            ResearchIdempotencyInProgressError("Research request is already in progress."),
            409,
        ),
    ],
)
def test_create_research_run_maps_idempotency_errors(
    error: Exception,
    expected_status: int,
) -> None:
    fake_service = FakeResearchExecutionService(
        error=error,
    )

    app.dependency_overrides[get_research_execution_service] = lambda: fake_service
    override_current_session()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/research-runs",
                headers={
                    "Idempotency-Key": "request-123",
                },
                json={
                    "query": "What is a mutex?",
                    "llm_provider": "qwen",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == expected_status
    assert response.json()["detail"] == str(error)


def test_create_research_run_rejects_long_idempotency_key() -> None:
    fake_service = FakeResearchExecutionService()

    app.dependency_overrides[get_research_execution_service] = lambda: fake_service
    override_current_session()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/research-runs",
                headers={
                    "Idempotency-Key": "a" * 201,
                },
                json={
                    "query": "What is a mutex?",
                    "llm_provider": "qwen",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert fake_service.calls == []


def test_create_research_run_rejects_request_above_rate_limit(
    research_rate_limiter: FakeResearchRateLimiter,
) -> None:
    research_rate_limiter.decision = ResearchRateLimitDecision(
        allowed=False,
        limit=2,
        remaining=0,
        reset_after_seconds=37,
    )
    fake_service = FakeResearchExecutionService()
    app.dependency_overrides[get_research_execution_service] = lambda: fake_service
    override_current_session()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/research-runs",
                json={
                    "query": "What is a mutex?",
                    "llm_provider": "qwen",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 429
    assert response.json()["detail"] == "Research request rate limit exceeded."
    assert response.headers["X-RateLimit-Limit"] == "2"
    assert response.headers["X-RateLimit-Remaining"] == "0"
    assert response.headers["X-RateLimit-Reset"] == "37"
    assert response.headers["Retry-After"] == "37"
    assert fake_service.calls == []


def test_create_research_run_fails_closed_when_rate_limiter_is_unavailable(
    research_rate_limiter: FakeResearchRateLimiter,
) -> None:
    research_rate_limiter.error = ResearchRateLimitUnavailableError(
        "Research rate limiting is unavailable."
    )
    fake_service = FakeResearchExecutionService()
    app.dependency_overrides[get_research_execution_service] = lambda: fake_service
    override_current_session()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/research-runs",
                json={
                    "query": "What is a mutex?",
                    "llm_provider": "qwen",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"] == "Research rate limiting is unavailable."
    assert fake_service.calls == []


def test_cancel_research_job_is_tenant_scoped() -> None:
    tenant_id = uuid4()
    research_run_id = uuid4()
    manager = FakeResearchJobManager(research_run_id)
    app.dependency_overrides[get_research_job_manager] = lambda: manager
    override_current_session(tenant_id=tenant_id)

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/research-runs/{research_run_id}/cancel",
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "research_run_id": str(research_run_id),
        "status": "cancelled",
    }
    assert manager.cancel_calls == [(tenant_id, research_run_id)]


def test_cancel_research_job_rejects_terminal_or_missing_run() -> None:
    manager = FakeResearchJobManager(cancel_result=False)
    app.dependency_overrides[get_research_job_manager] = lambda: manager
    override_current_session()

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/research-runs/{uuid4()}/cancel",
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["detail"] == "Research run is not active or was not found."


def test_get_research_run_returns_tenant_scoped_lifecycle_state() -> None:
    tenant_id = uuid4()
    research_run_id = uuid4()
    run = ResearchRun(
        id=research_run_id,
        tenant_id=tenant_id,
        query="Compare HTTP/2 and HTTP/3.",
        llm_provider="anthropic",
        status="completed",
        route="deep_research",
        route_reason="Comparison requires current sources.",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    store = FakeResearchRunStore(run)
    app.dependency_overrides[get_research_run_store] = lambda: store
    override_current_session(tenant_id=tenant_id)

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/research-runs/{research_run_id}",
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["research_run_id"] == str(research_run_id)
    assert body["status"] == "completed"
    assert body["route"] == "deep_research"
    assert body["query"] == "Compare HTTP/2 and HTTP/3."
    assert store.calls == [(tenant_id, research_run_id)]


def test_get_research_run_returns_404_when_missing() -> None:
    store = FakeResearchRunStore(None)
    app.dependency_overrides[get_research_run_store] = lambda: store
    override_current_session()

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/research-runs/{uuid4()}",
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "Research run was not found."


def test_list_research_runs_returns_tenant_scoped_history() -> None:
    tenant_id = uuid4()
    runs = [
        ResearchRun(
            id=uuid4(),
            tenant_id=tenant_id,
            query="Compare HTTP/2 and HTTP/3.",
            llm_provider="anthropic",
            status="completed",
            route="deep_research",
            created_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        ResearchRun(
            id=uuid4(),
            tenant_id=tenant_id,
            query="What is a mutex?",
            llm_provider="ollama",
            status="completed",
            route="direct",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
    ]
    store = FakeResearchRunStore(runs=runs)
    app.dependency_overrides[get_research_run_store] = lambda: store
    override_current_session(tenant_id=tenant_id)

    try:
        with TestClient(app) as client:
            response = client.get(
                "/research-runs",
                params={"limit": 5},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert [item["query"] for item in body] == ["Compare HTTP/2 and HTTP/3.", "What is a mutex?"]
    assert store.list_calls == [(tenant_id, 5)]


def test_list_research_runs_rejects_out_of_range_limit() -> None:
    store = FakeResearchRunStore(runs=[])
    app.dependency_overrides[get_research_run_store] = lambda: store
    override_current_session()

    try:
        with TestClient(app) as client:
            response = client.get(
                "/research-runs",
                params={"limit": 0},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
