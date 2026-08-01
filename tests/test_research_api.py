from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_research_execution_service,
    get_research_progress_store,
    get_research_rate_limiter,
)
from app.main import app
from app.schemas.progress import ResearchProgressRecord
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
    ) -> None:
        self.idempotency_replayed = idempotency_replayed
        self.error = error
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
        state: ResearchState = {
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


@pytest.fixture(autouse=True)
def research_rate_limiter() -> Iterator[FakeResearchRateLimiter]:
    limiter = FakeResearchRateLimiter()
    app.dependency_overrides[get_research_rate_limiter] = lambda: limiter

    yield limiter

    app.dependency_overrides.clear()


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
