from typing import TypedDict


class ResearchState(TypedDict):
    """Represent the shared state passed between research workflow nodes."""

    query: str
    status: str