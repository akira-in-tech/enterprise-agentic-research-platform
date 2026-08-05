from typing import Literal

from pydantic import BaseModel


class ProviderCapabilityResponse(BaseModel):
    """Describe one user-selectable research model provider."""

    id: Literal["claude", "qwen"]
    canonical_provider: Literal["anthropic", "ollama"]
    label: str
    execution: Literal["cloud", "local"]
    configured: bool


class ReadinessResponse(BaseModel):
    """Describe whether required durable dependencies accept traffic."""

    status: Literal["ready"]
    postgresql: Literal["ready"]
    redis: Literal["ready"]
