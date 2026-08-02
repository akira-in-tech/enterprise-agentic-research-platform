from typing import NotRequired, TypedDict
from uuid import UUID

from app.schemas.evidence import (
    CitationAudit,
    EvidenceScore,
    EvidenceSource,
    ReflectionDecision,
)
from app.schemas.intent import ResearchRoute
from app.schemas.planner import ResearchPlan
from app.schemas.source import PrivateSource, WebSource
from app.schemas.workflow import (
    EvidenceConflict,
    EvidenceGap,
    ResearchAgentRole,
    ResearchFinding,
    SupplementaryResearchQuery,
)
from app.services.search.executor import ResearchTaskResult


class ResearchState(TypedDict):
    """Represent the shared state passed between workflow nodes."""

    query: str
    tenant_id: NotRequired[UUID]
    status: NotRequired[str]
    active_agent: NotRequired[ResearchAgentRole]
    route: NotRequired[ResearchRoute]
    route_reason: NotRequired[str]
    answer: NotRequired[str]
    plan: NotRequired[ResearchPlan]
    web_search_results: NotRequired[list[ResearchTaskResult]]
    web_sources: NotRequired[list[WebSource]]
    private_sources: NotRequired[list[PrivateSource]]
    local_scout_errors: NotRequired[list[str]]
    evidence_sources: NotRequired[list[EvidenceSource]]
    evidence_scores: NotRequired[list[EvidenceScore]]
    evidence_gaps: NotRequired[list[EvidenceGap]]
    evidence_conflicts: NotRequired[list[EvidenceConflict]]
    analysis_findings: NotRequired[list[ResearchFinding]]
    supplementary_queries: NotRequired[list[SupplementaryResearchQuery]]
    iteration: NotRequired[int]
    max_iterations: NotRequired[int]
    draft_report: NotRequired[str]
    report: NotRequired[str]
    citation_audit: NotRequired[CitationAudit]
    reflection: NotRequired[ReflectionDecision]
    reflection_attempts: NotRequired[int]
