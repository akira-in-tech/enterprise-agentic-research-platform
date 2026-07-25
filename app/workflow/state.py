from typing import NotRequired, TypedDict

from app.schemas.intent import ResearchRoute
from app.schemas.planner import ResearchPlan
from app.services.search.base import SearchResult
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
    web_sources: NotRequired[list[SearchResult]]