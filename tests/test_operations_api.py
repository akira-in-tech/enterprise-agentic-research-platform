from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.api.dependencies import get_readiness_service
from app.core.config import settings
from app.main import app
from app.schemas.operations import ReadinessResponse
from app.services.readiness import ApplicationReadinessService


def test_provider_capabilities_are_stable_and_do_not_expose_secrets() -> None:
    with TestClient(app) as client:
        response = client.get("/providers")

    assert response.status_code == 200
    assert [provider["id"] for provider in response.json()] == ["claude", "qwen"]
    assert {provider["canonical_provider"] for provider in response.json()} == {
        "anthropic",
        "ollama",
    }
    assert "api_key" not in response.text.lower()
    secret = settings.anthropic_api_key.get_secret_value()
    if secret:
        assert secret not in response.text


def test_ready_returns_dependency_status() -> None:
    service = AsyncMock(spec=ApplicationReadinessService)
    service.check.return_value = ReadinessResponse(
        status="ready",
        postgresql="ready",
        redis="ready",
    )
    app.dependency_overrides[get_readiness_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.get("/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "postgresql": "ready",
        "redis": "ready",
    }


def test_ready_fails_closed_without_dependency_details() -> None:
    service = AsyncMock(spec=ApplicationReadinessService)
    service.check.side_effect = RuntimeError("postgresql password must stay private")
    app.dependency_overrides[get_readiness_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.get("/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"detail": "Required application dependencies are unavailable."}
    assert "password" not in response.text
