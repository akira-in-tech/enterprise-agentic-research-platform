from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ResearchReportSourceResponse(BaseModel):
    """Represent one durable report source returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    source_id: str
    origin: Literal["web", "private", "mcp"]
    title: str
    locator: str
    provider: str
    relevance: float = Field(ge=0, le=1)
    content_quality: float = Field(ge=0, le=1)
    traceability: float = Field(ge=0, le=1)
    overall_score: float = Field(ge=0, le=1)
    cited: bool
    source_type: Literal["web", "paper"] = "web"
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None


class ResearchReportResponse(BaseModel):
    """Represent one durable tenant-scoped research report."""

    report_id: UUID
    research_run_id: UUID
    content: str
    workflow_status: str
    citation_valid: bool
    citation_coverage: float = Field(ge=0, le=1)
    reflection_status: Literal["approved", "revise"]
    reflection_reasons: list[str]
    reflection_attempts: int = Field(ge=1)
    created_at: datetime
    sources: list[ResearchReportSourceResponse]


class ResearchReportExportResponse(BaseModel):
    """Represent one exported report snapshot's durable storage location."""

    storage_key: str
