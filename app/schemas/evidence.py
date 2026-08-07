from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EvidenceOrigin = Literal["web", "private", "mcp"]


class EvidenceSource(BaseModel):
    """Represent provider-neutral evidence available to an analyst."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(pattern=r"^(WEB|PRIVATE|MCP|PAPER)-[0-9A-F]{16}$")
    origin: EvidenceOrigin
    title: str = Field(min_length=1, max_length=500)
    locator: str = Field(min_length=1, max_length=2048)
    content: str = Field(min_length=1, max_length=20_000)
    provider: str = Field(min_length=1, max_length=100)
    retrieval_score: float | None = Field(default=None, ge=-1.0, le=1.0)
    source_type: Literal["web", "paper"] = "web"
    authors: list[str] = Field(default_factory=list, max_length=20)
    year: int | None = Field(default=None, ge=1000, le=2100)
    venue: str | None = Field(default=None, max_length=300)


class EvidenceScore(BaseModel):
    """Explain the deterministic quality score for one evidence source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    relevance: float = Field(ge=0.0, le=1.0)
    content_quality: float = Field(ge=0.0, le=1.0)
    traceability: float = Field(ge=0.0, le=1.0)
    overall: float = Field(ge=0.0, le=1.0)


class CitationAudit(BaseModel):
    """Represent citation integrity and paragraph-level coverage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    valid: bool
    cited_source_ids: list[str]
    unknown_source_ids: list[str]
    uncited_claims: list[str]
    coverage_ratio: float = Field(ge=0.0, le=1.0)


class ReflectionDecision(BaseModel):
    """Represent the quality gate applied to an analyst report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["approved", "revise"]
    reasons: list[str]
    evidence_count: int = Field(ge=0)
    average_evidence_score: float = Field(ge=0.0, le=1.0)
    human_review_required: bool = False
    human_review_reason: str | None = Field(default=None, max_length=500)
