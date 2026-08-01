from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_research_execution_service,
)
from app.main import app
from app.services.research.execution import (
    ResearchExecutionResult,
)
from app.services.research.idempotency import (
    ResearchIdempotencyConflictError,
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


def test_create_research_run_accepts_qwen_selection() -> None:
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
