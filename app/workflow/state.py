from typing import Literal, NotRequired, TypedDict

ResearchRoute = Literal["direct", "deep_research"]


class ResearchState(TypedDict):
    """Represent the shared state passed between research workflow nodes."""

    query: str
    status: str
    route: NotRequired[ResearchRoute]