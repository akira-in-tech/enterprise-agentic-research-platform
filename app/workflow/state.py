from typing import NotRequired, TypedDict

from app.schemas.evidence import (
    CitationAudit,
    EvidenceScore,
    EvidenceSource,
    ReflectionDecision,
)
from app.schemas.intent import ResearchRoute
from app.schemas.planner import ResearchPlan
from app.schemas.source import WebSource
from app.services.search.executor import ResearchTaskResult


class ResearchState(TypedDict):
    """Represent the shared state passed between workflow nodes."""

    query: str
    status: NotRequired[str]
    route: NotRequired[ResearchRoute]
    route_reason: NotRequired[str]
    answer: NotRequired[str]
    plan: NotRequired[ResearchPlan]
    web_search_results: NotRequired[list[ResearchTaskResult]]
    web_sources: NotRequired[list[WebSource]]
    evidence_sources: NotRequired[list[EvidenceSource]]
    evidence_scores: NotRequired[list[EvidenceScore]]
    report: NotRequired[str]
    citation_audit: NotRequired[CitationAudit]
    reflection: NotRequired[ReflectionDecision]
