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
    ReflectionResult,
    ResearchAgentRole,
    ResearchAnalysis,
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
    is_high_risk_domain: NotRequired[bool]
    answer: NotRequired[str]
    plan: NotRequired[ResearchPlan]
    web_search_results: NotRequired[list[ResearchTaskResult]]
    web_sources: NotRequired[list[WebSource]]
    web_scout_status: NotRequired[str]
    private_sources: NotRequired[list[PrivateSource]]
    local_scout_errors: NotRequired[list[str]]
    local_scout_status: NotRequired[str]
    mcp_sources: NotRequired[list[EvidenceSource]]
    mcp_scout_errors: NotRequired[list[str]]
    mcp_scout_status: NotRequired[str]
    evidence_sources: NotRequired[list[EvidenceSource]]
    evidence_scores: NotRequired[list[EvidenceScore]]
    evidence_gaps: NotRequired[list[EvidenceGap]]
    evidence_conflicts: NotRequired[list[EvidenceConflict]]
    analysis: NotRequired[ResearchAnalysis]
    analysis_findings: NotRequired[list[ResearchFinding]]
    reflection_result: NotRequired[ReflectionResult]
    supplementary_queries: NotRequired[list[SupplementaryResearchQuery]]
    attempted_queries: NotRequired[list[str]]
    iteration: NotRequired[int]
    max_iterations: NotRequired[int]
    draft_report: NotRequired[str]
    report: NotRequired[str]
    citation_audit: NotRequired[CitationAudit]
    reflection: NotRequired[ReflectionDecision]
    reflection_attempts: NotRequired[int]
