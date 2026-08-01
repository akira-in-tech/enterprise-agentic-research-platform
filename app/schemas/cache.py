from pydantic import BaseModel, ConfigDict, Field

from app.schemas.evidence import (
    CitationAudit,
    EvidenceScore,
    EvidenceSource,
    ReflectionDecision,
)
from app.schemas.intent import ResearchRoute
from app.schemas.research import PersistedLLMProvider


class CachedResearchResult(BaseModel):
    """Represent the stable JSON payload stored in Redis."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    llm_provider: PersistedLLMProvider
    workflow_status: str = Field(
        min_length=1,
        max_length=100,
    )
    route: ResearchRoute | None = None
    route_reason: str | None = Field(
        default=None,
        min_length=1,
        max_length=300,
    )
    answer: str | None = Field(
        default=None,
        min_length=1,
    )
    citation_audit: CitationAudit | None = None
    reflection: ReflectionDecision | None = None
    report: str | None = Field(default=None, min_length=1)
    evidence_sources: list[EvidenceSource] = Field(default_factory=list)
    evidence_scores: list[EvidenceScore] = Field(default_factory=list)
    reflection_attempts: int | None = Field(default=None, ge=1)
