from typing import NotRequired, TypedDict

from app.schemas.intent import ResearchRoute
from app.schemas.planner import ResearchPlan


class ResearchState(TypedDict):
    """Represent the shared state passed between workflow nodes."""

    query: str
    status: str
    route: NotRequired[ResearchRoute]
    route_reason: NotRequired[str]
    plan: NotRequired[ResearchPlan]