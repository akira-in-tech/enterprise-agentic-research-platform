from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies import get_auth_service
from app.db.models import Tenant, User
from app.main import app
from app.services.auth import (
    AuthenticatedIdentity,
    AuthenticatedSession,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    ResolvedSession,
)


class FakeAuthService:
    def __init__(
        self,
        *,
        authenticated_session: AuthenticatedSession | None = None,
        register_error: Exception | None = None,
        login_error: Exception | None = None,
        resolved_session: ResolvedSession | None = None,
        profile: AuthenticatedIdentity | None = None,
        updated_profile: AuthenticatedIdentity | None = None,
        change_password_error: Exception | None = None,
    ) -> None:
        self.authenticated_session = authenticated_session
        self.register_error = register_error
        self.login_error = login_error
        self.resolved_session = resolved_session
        self.profile = profile
        self.updated_profile = updated_profile
        self.change_password_error = change_password_error
        self.logout_calls: list[str] = []
        self.update_display_name_calls: list[dict[str, object]] = []
        self.change_password_calls: list[dict[str, object]] = []

    async def register(
        self,
        *,
        email: str,
        password: str,
        tenant_name: str,
        display_name: str | None = None,
    ) -> AuthenticatedSession:
        if self.register_error is not None:
            raise self.register_error

        assert self.authenticated_session is not None
        return self.authenticated_session

    async def login(
        self,
        *,
        email: str,
        password: str,
    ) -> AuthenticatedSession:
        if self.login_error is not None:
            raise self.login_error

        assert self.authenticated_session is not None
        return self.authenticated_session

    async def logout(
        self,
        *,
        token: str,
    ) -> None:
        self.logout_calls.append(token)

    async def resolve_session(
        self,
        *,
        token: str,
    ) -> ResolvedSession | None:
        return self.resolved_session

    async def get_profile(
        self,
        *,
        user_id: object,
        tenant_id: object,
    ) -> AuthenticatedIdentity | None:
        return self.profile

    async def update_display_name(
        self,
        *,
        user_id: object,
        tenant_id: object,
        display_name: str | None,
    ) -> AuthenticatedIdentity | None:
        self.update_display_name_calls.append(
            {
                "user_id": user_id,
                "tenant_id": tenant_id,
                "display_name": display_name,
            }
        )
        return self.updated_profile

    async def change_password(
        self,
        *,
        user_id: object,
        tenant_id: object,
        current_password: str,
        new_password: str,
    ) -> None:
        self.change_password_calls.append(
            {
                "user_id": user_id,
                "tenant_id": tenant_id,
                "current_password": current_password,
                "new_password": new_password,
            }
        )
        if self.change_password_error is not None:
            raise self.change_password_error


def create_identity() -> AuthenticatedIdentity:
    tenant = Tenant(
        id=uuid4(),
        slug="acme-platform-a1b2c3d4",
        name="ACME Platform",
    )
    user = User(
        id=uuid4(),
        tenant_id=tenant.id,
        email="engineer@acme.example",
        password_hash="irrelevant",
        display_name="ACME Engineer",
    )

    return AuthenticatedIdentity(
        user=user,
        tenant=tenant,
    )


def create_authenticated_session() -> AuthenticatedSession:
    return AuthenticatedSession(
        identity=create_identity(),
        token="opaque-session-token",
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )


def test_register_sets_session_cookie_and_returns_identity() -> None:
    authenticated_session = create_authenticated_session()
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(
        authenticated_session=authenticated_session,
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                "/auth/register",
                json={
                    "email": "engineer@acme.example",
                    "password": "correct-horse-battery",
                    "tenant_name": "ACME Platform",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["user"]["email"] == "engineer@acme.example"
    assert response.json()["tenant"]["name"] == "ACME Platform"
    assert client.cookies.get("session_token") == "opaque-session-token"


def test_register_rejects_duplicate_email() -> None:
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(
        register_error=EmailAlreadyRegisteredError("Email is already registered."),
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                "/auth/register",
                json={
                    "email": "engineer@acme.example",
                    "password": "correct-horse-battery",
                    "tenant_name": "ACME Platform",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409


def test_register_rejects_short_password() -> None:
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/auth/register",
                json={
                    "email": "engineer@acme.example",
                    "password": "short",
                    "tenant_name": "ACME Platform",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_login_sets_session_cookie_and_returns_identity() -> None:
    authenticated_session = create_authenticated_session()
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(
        authenticated_session=authenticated_session,
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                "/auth/login",
                json={
                    "email": "engineer@acme.example",
                    "password": "correct-horse-battery",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert client.cookies.get("session_token") == "opaque-session-token"


def test_login_rejects_invalid_credentials() -> None:
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(
        login_error=InvalidCredentialsError("Invalid email or password."),
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                "/auth/login",
                json={
                    "email": "engineer@acme.example",
                    "password": "wrong-password",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


def test_logout_revokes_session_and_clears_cookie() -> None:
    fake_service = FakeAuthService()
    app.dependency_overrides[get_auth_service] = lambda: fake_service

    try:
        with TestClient(app) as client:
            client.cookies.set("session_token", "opaque-session-token")
            response = client.post("/auth/logout")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert fake_service.logout_calls == ["opaque-session-token"]
    set_cookie_header = response.headers["set-cookie"]
    assert "session_token=" in set_cookie_header
    assert "Max-Age=0" in set_cookie_header


def test_logout_without_cookie_is_a_no_op() -> None:
    fake_service = FakeAuthService()
    app.dependency_overrides[get_auth_service] = lambda: fake_service

    try:
        with TestClient(app) as client:
            response = client.post("/auth/logout")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert fake_service.logout_calls == []


def test_me_returns_current_identity_when_authenticated() -> None:
    identity = create_identity()
    resolved_session = ResolvedSession(
        user_id=identity.user.id,
        tenant_id=identity.tenant.id,
    )
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(
        resolved_session=resolved_session,
        profile=identity,
    )

    try:
        with TestClient(app) as client:
            client.cookies.set("session_token", "opaque-session-token")
            response = client.get("/auth/me")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["user"]["email"] == identity.user.email


def test_me_rejects_missing_session_cookie() -> None:
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService()

    try:
        with TestClient(app) as client:
            response = client.get("/auth/me")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


def test_me_rejects_unresolvable_session() -> None:
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(
        resolved_session=None,
    )

    try:
        with TestClient(app) as client:
            client.cookies.set("session_token", "stale-token")
            response = client.get("/auth/me")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


def test_update_profile_renames_the_caller() -> None:
    identity = create_identity()
    resolved_session = ResolvedSession(
        user_id=identity.user.id,
        tenant_id=identity.tenant.id,
    )
    renamed_identity = AuthenticatedIdentity(
        user=User(
            id=identity.user.id,
            tenant_id=identity.tenant.id,
            email=identity.user.email,
            password_hash="irrelevant",
            display_name="New Name",
        ),
        tenant=identity.tenant,
    )
    fake_service = FakeAuthService(
        resolved_session=resolved_session,
        updated_profile=renamed_identity,
    )
    app.dependency_overrides[get_auth_service] = lambda: fake_service

    try:
        with TestClient(app) as client:
            client.cookies.set("session_token", "opaque-session-token")
            response = client.patch(
                "/auth/profile",
                json={"display_name": "New Name"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["user"]["display_name"] == "New Name"
    assert fake_service.update_display_name_calls == [
        {
            "user_id": identity.user.id,
            "tenant_id": identity.tenant.id,
            "display_name": "New Name",
        }
    ]


def test_update_profile_requires_authentication() -> None:
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(
        resolved_session=None,
    )

    try:
        with TestClient(app) as client:
            response = client.patch(
                "/auth/profile",
                json={"display_name": "New Name"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


def test_update_profile_rejects_overlong_display_name() -> None:
    identity = create_identity()
    resolved_session = ResolvedSession(
        user_id=identity.user.id,
        tenant_id=identity.tenant.id,
    )
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(
        resolved_session=resolved_session,
        profile=identity,
    )

    try:
        with TestClient(app) as client:
            client.cookies.set("session_token", "opaque-session-token")
            response = client.patch(
                "/auth/profile",
                json={"display_name": "a" * 201},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_change_password_succeeds() -> None:
    identity = create_identity()
    resolved_session = ResolvedSession(
        user_id=identity.user.id,
        tenant_id=identity.tenant.id,
    )
    fake_service = FakeAuthService(resolved_session=resolved_session)
    app.dependency_overrides[get_auth_service] = lambda: fake_service

    try:
        with TestClient(app) as client:
            client.cookies.set("session_token", "opaque-session-token")
            response = client.post(
                "/auth/change-password",
                json={
                    "current_password": "correct-horse-battery",
                    "new_password": "new-correct-horse-battery",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert fake_service.change_password_calls == [
        {
            "user_id": identity.user.id,
            "tenant_id": identity.tenant.id,
            "current_password": "correct-horse-battery",
            "new_password": "new-correct-horse-battery",
        }
    ]


def test_change_password_rejects_wrong_current_password() -> None:
    identity = create_identity()
    resolved_session = ResolvedSession(
        user_id=identity.user.id,
        tenant_id=identity.tenant.id,
    )
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(
        resolved_session=resolved_session,
        change_password_error=InvalidCredentialsError("Current password is incorrect."),
    )

    try:
        with TestClient(app) as client:
            client.cookies.set("session_token", "opaque-session-token")
            response = client.post(
                "/auth/change-password",
                json={
                    "current_password": "wrong-password",
                    "new_password": "new-correct-horse-battery",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


def test_change_password_rejects_short_new_password() -> None:
    identity = create_identity()
    resolved_session = ResolvedSession(
        user_id=identity.user.id,
        tenant_id=identity.tenant.id,
    )
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(
        resolved_session=resolved_session,
    )

    try:
        with TestClient(app) as client:
            client.cookies.set("session_token", "opaque-session-token")
            response = client.post(
                "/auth/change-password",
                json={
                    "current_password": "correct-horse-battery",
                    "new_password": "short",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_change_password_requires_authentication() -> None:
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(
        resolved_session=None,
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                "/auth/change-password",
                json={
                    "current_password": "correct-horse-battery",
                    "new_password": "new-correct-horse-battery",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
