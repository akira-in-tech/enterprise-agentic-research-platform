from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RegisterRequest(BaseModel):
    """Represent a self-service tenant signup request."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
    )

    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=8, max_length=256)
    tenant_name: str = Field(min_length=1, max_length=200)
    display_name: str | None = Field(default=None, max_length=200)


class LoginRequest(BaseModel):
    """Represent a login request."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
    )

    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class UpdateProfileRequest(BaseModel):
    """Represent a request to change the caller's display name."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
    )

    display_name: str | None = Field(default=None, max_length=200)


class ChangePasswordRequest(BaseModel):
    """Represent a request to change the caller's password."""

    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class UserResponse(BaseModel):
    """Represent one authenticated tenant user."""

    id: UUID
    email: str
    display_name: str | None = None


class TenantResponse(BaseModel):
    """Represent one authenticated user's tenant."""

    id: UUID
    name: str
    slug: str


class AuthResponse(BaseModel):
    """Represent the identity behind the current session."""

    user: UserResponse
    tenant: TenantResponse
