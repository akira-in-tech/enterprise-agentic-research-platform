from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.core.config import parse_cors_allowed_origins


def test_default_app_adds_no_cors_middleware_when_unconfigured() -> None:
    from app.main import app

    assert not any(
        getattr(middleware.cls, "__name__", "") == "CORSMiddleware"
        for middleware in app.user_middleware
    )


def build_cors_app(origins_env: str) -> FastAPI:
    """Mirror app/main.py's exact CORS wiring for isolated behavioral testing."""

    app = FastAPI()

    @app.get("/probe")
    def probe() -> dict[str, bool]:
        return {"ok": True}

    allowed_origins = parse_cors_allowed_origins(origins_env)
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Correlation-ID"],
        )

    return app


def test_configured_origin_receives_cors_headers() -> None:
    client = TestClient(build_cors_app("https://console.example.com"))

    response = client.get(
        "/probe",
        headers={"Origin": "https://console.example.com"},
    )

    assert response.headers["access-control-allow-origin"] == "https://console.example.com"


def test_configured_origin_allows_credentialed_requests() -> None:
    """Session cookies require allow_credentials, which forbids a wildcard origin."""

    client = TestClient(build_cors_app("https://console.example.com"))

    response = client.get(
        "/probe",
        headers={"Origin": "https://console.example.com"},
    )

    assert response.headers["access-control-allow-credentials"] == "true"


def test_unlisted_origin_receives_no_cors_headers() -> None:
    client = TestClient(build_cors_app("https://console.example.com"))

    response = client.get(
        "/probe",
        headers={"Origin": "https://attacker.example.com"},
    )

    assert "access-control-allow-origin" not in response.headers


def test_preflight_request_reports_allowed_methods_and_headers() -> None:
    client = TestClient(build_cors_app("https://console.example.com"))

    response = client.options(
        "/probe",
        headers={
            "Origin": "https://console.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-Tenant-ID",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://console.example.com"
    assert "POST" in response.headers["access-control-allow-methods"]
