from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.intent import ResearchRoute

ResearchRunStatus = Literal[
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
]

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
    document_ids: list[UUID] | None = Field(
        default=None,
        description=(
            "Scope private-knowledge retrieval to these documents. Omit or "
            "pass null to search every ready tenant document; pass an empty "
            "list to search none."
        ),
    )


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
    citation_valid: bool | None = None
    citation_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    reflection_status: Literal["approved", "revise"] | None = None
    reflection_reasons: list[str] = Field(default_factory=list)
    human_review_required: bool = False
    human_review_reason: str | None = None


class CreateResearchJobResponse(BaseModel):
    """Represent one accepted asynchronous research job."""

    research_run_id: UUID
    status: Literal["queued"]
    progress_url: str
    events_url: str
    report_url: str


class CancelResearchRunResponse(BaseModel):
    """Confirm one durable research cancellation."""

    research_run_id: UUID
    status: Literal["cancelled"]


class ResearchRunResponse(BaseModel):
    """Represent one durable research run's current lifecycle state."""

    research_run_id: UUID
    llm_provider: PersistedLLMProvider
    status: ResearchRunStatus
    query: str
    route: ResearchRoute | None = None
    route_reason: str | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
