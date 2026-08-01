from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.intent import ResearchRoute

UserFacingLLMProvider = Literal[
    "claude",
    "qwen",
]

PersistedLLMProvider = Literal[
    "anthropic",
    "ollama",
]


class CreateResearchRunRequest(BaseModel):
    """Represent a user request to start one research run."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
    )

    query: str = Field(
        min_length=1,
    )
    llm_provider: UserFacingLLMProvider


class CreateResearchRunResponse(BaseModel):
    """Represent one completed synchronous research request."""

    research_run_id: UUID
    llm_provider: PersistedLLMProvider
    status: Literal["completed"]
    cache_hit: bool
    idempotency_replayed: bool = False
    workflow_status: str
    route: ResearchRoute | None = None
    route_reason: str | None = None
    answer: str | None = None
