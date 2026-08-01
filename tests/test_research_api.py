from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_research_execution_service,
    get_research_job_manager,
    get_research_progress_store,
    get_research_rate_limiter,
    get_research_report_store,
)
from app.main import app
from app.schemas.evidence import CitationAudit, ReflectionDecision
from app.schemas.progress import ResearchProgressRecord
from app.schemas.report import ResearchReportResponse
from app.services.cache import (
    CacheUnavailableError,
    ResearchRateLimitDecision,
    ResearchRateLimitUnavailableError,
)
from app.services.research.execution import (
    ResearchExecutionResult,
)
from app.services.research.idempotency import (
    ResearchIdempotencyConflictError,
    ResearchIdempotencyInProgressError,
    ResearchIdempotencyUnavailableError,
)
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
    ) -> ResearchExecutionResult:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "query": query,
                "llm_provider": llm_provider,
                "requested_by_user_id": requested_by_user_id,
                "idempotency_key": idempotency_key,
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
    def __init__(self, research_run_id: UUID | None = None) -> None:
        self.research_run_id = research_run_id or uuid4()
        self.calls: list[dict[str, object]] = []

    async def submit(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: str,
        requested_by_user_id: UUID | None = None,
    ) -> UUID:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "query": query,
                "llm_provider": llm_provider,
                "requested_by_user_id": requested_by_user_id,
            }
        )
        return self.research_run_id


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

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/research-runs/{research_run_id}/progress",
                headers={"X-Tenant-ID": str(tenant_id)},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert progress_store.calls == [(tenant_id, research_run_id)]


def test_get_research_progress_returns_not_found() -> None:
    progress_store = FakeResearchProgressStore()
    app.dependency_overrides[get_research_progress_store] = lambda: progress_store

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/research-runs/{uuid4()}/progress",
                headers={"X-Tenant-ID": str(uuid4())},
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

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/research-runs/{uuid4()}/progress",
                headers={"X-Tenant-ID": str(uuid4())},
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

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/research-runs/{research_run_id}/events",
                headers={"X-Tenant-ID": str(tenant_id)},
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

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/research-runs/{research_run_id}/report",
                headers={"X-Tenant-ID": str(tenant_id)},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["content"] == "Durable report."
    assert report_store.calls == [(tenant_id, research_run_id)]


def test_get_research_report_returns_not_found() -> None:
    report_store = FakeResearchReportStore()
    app.dependency_overrides[get_research_report_store] = lambda: report_store

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/research-runs/{uuid4()}/report",
                headers={"X-Tenant-ID": str(uuid4())},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Research report was not found."}


@pytest.fixture(autouse=True)
def research_rate_limiter() -> Iterator[FakeResearchRateLimiter]:
    limiter = FakeResearchRateLimiter()
    app.dependency_overrides[get_research_rate_limiter] = lambda: limiter

    yield limiter

    app.dependency_overrides.clear()


def test_create_research_job_returns_durable_delivery_urls(
    research_rate_limiter: FakeResearchRateLimiter,
) -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    research_run_id = uuid4()
    job_manager = FakeResearchJobManager(research_run_id)
    app.dependency_overrides[get_research_job_manager] = lambda: job_manager

    try:
        with TestClient(app) as client:
            response = client.post(
                "/research-runs/jobs",
                headers={
                    "X-Tenant-ID": str(tenant_id),
                    "X-User-ID": str(user_id),
                },
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
        }
    ]
    assert research_rate_limiter.calls == [tenant_id]


def test_create_research_run_accepts_qwen_selection(
    research_rate_limiter: FakeResearchRateLimiter,
) -> None:
    fake_service = FakeResearchExecutionService()
    tenant_id = uuid4()
    user_id = uuid4()

    app.dependency_overrides[get_research_execution_service] = lambda: fake_service

    try:
        with TestClient(app) as client:
            response = client.post(
                "/research-runs",
                headers={
                    "X-Tenant-ID": str(tenant_id),
                    "X-User-ID": str(user_id),
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

    try:
        with TestClient(app) as client:
            response = client.post(
                "/research-runs",
                headers={"X-Tenant-ID": str(uuid4())},
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

    try:
        with TestClient(app) as client:
            response = client.post(
                "/research-runs",
                headers={
                    "X-Tenant-ID": str(uuid4()),
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

    try:
        with TestClient(app) as client:
            response = client.post(
                "/research-runs",
                headers={
                    "X-Tenant-ID": str(uuid4()),
                },
                json={
                    "query": "Explain DNS recursive resolution.",
                    "llm_provider": "openai",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert fake_service.calls == []


def test_create_research_run_requires_tenant_header() -> None:
    fake_service = FakeResearchExecutionService()

    app.dependency_overrides[get_research_execution_service] = lambda: fake_service

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

    assert response.status_code == 422
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

    try:
        with TestClient(app) as client:
            response = client.post(
                "/research-runs",
                headers={
                    "X-Tenant-ID": str(uuid4()),
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

    try:
        with TestClient(app) as client:
            response = client.post(
                "/research-runs",
                headers={
                    "X-Tenant-ID": str(uuid4()),
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

    try:
        with TestClient(app) as client:
            response = client.post(
                "/research-runs",
                headers={
                    "X-Tenant-ID": str(uuid4()),
                },
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

    try:
        with TestClient(app) as client:
            response = client.post(
                "/research-runs",
                headers={
                    "X-Tenant-ID": str(uuid4()),
                },
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
