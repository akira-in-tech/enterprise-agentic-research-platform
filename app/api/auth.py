from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.dependencies import get_auth_service, get_current_session
from app.core.config import settings
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    TenantResponse,
    UpdateProfileRequest,
    UserResponse,
)
from app.services.auth import (
    AuthenticatedIdentity,
    AuthenticatedSession,
    AuthService,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    ResolvedSession,
)

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


def _set_session_cookie(
    response: Response,
    authenticated_session: AuthenticatedSession,
) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=authenticated_session.token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        path="/",
    )


def _to_auth_response(
    identity: AuthenticatedIdentity,
) -> AuthResponse:
    return AuthResponse(
        user=UserResponse(
            id=identity.user.id,
            email=identity.user.email,
            display_name=identity.user.display_name,
        ),
        tenant=TenantResponse(
            id=identity.tenant.id,
            name=identity.tenant.name,
            slug=identity.tenant.slug,
        ),
    )


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    body: RegisterRequest,
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthResponse:
    """Create a new tenant and its first user, then start a session."""

    try:
        authenticated_session = await auth_service.register(
            email=body.email,
            password=body.password,
            tenant_name=body.tenant_name,
            display_name=body.display_name,
        )
    except EmailAlreadyRegisteredError as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            str(error),
        ) from error

    _set_session_cookie(
        response,
        authenticated_session,
    )

    return _to_auth_response(authenticated_session.identity)


@router.post(
    "/login",
    response_model=AuthResponse,
)
async def login(
    body: LoginRequest,
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthResponse:
    """Authenticate a user by email and password and start a session."""

    try:
        authenticated_session = await auth_service.login(
            email=body.email,
            password=body.password,
        )
    except InvalidCredentialsError as error:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            str(error),
        ) from error

    _set_session_cookie(
        response,
        authenticated_session,
    )

    return _to_auth_response(authenticated_session.identity)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def logout(
    request: Request,
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    """Revoke the caller's session, if any, and clear the session cookie."""

    token = request.cookies.get(settings.session_cookie_name)

    if token:
        await auth_service.logout(token=token)

    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
    )


@router.get(
    "/me",
    response_model=AuthResponse,
)
async def read_current_user(
    current_session: Annotated[ResolvedSession, Depends(get_current_session)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthResponse:
    """Return the identity behind the caller's current session."""

    identity = await auth_service.get_profile(
        user_id=current_session.user_id,
        tenant_id=current_session.tenant_id,
    )

    if identity is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Not authenticated.",
        )

    return _to_auth_response(identity)


@router.patch(
    "/profile",
    response_model=AuthResponse,
)
async def update_profile(
    body: UpdateProfileRequest,
    current_session: Annotated[ResolvedSession, Depends(get_current_session)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthResponse:
    """Update the caller's display name within their own tenant boundary."""

    identity = await auth_service.update_display_name(
        user_id=current_session.user_id,
        tenant_id=current_session.tenant_id,
        display_name=body.display_name,
    )

    if identity is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Not authenticated.",
        )

    return _to_auth_response(identity)


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def change_password(
    body: ChangePasswordRequest,
    current_session: Annotated[ResolvedSession, Depends(get_current_session)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    """Change the caller's password after verifying their current one."""

    try:
        await auth_service.change_password(
            user_id=current_session.user_id,
            tenant_id=current_session.tenant_id,
            current_password=body.current_password,
            new_password=body.new_password,
        )
    except InvalidCredentialsError as error:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            str(error),
        ) from error
