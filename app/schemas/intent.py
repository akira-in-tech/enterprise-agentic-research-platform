from typing import Literal

from pydantic import BaseModel, Field

ResearchRoute = Literal["direct", "deep_research"]


class IntentDecision(BaseModel):
    """Represent the routing decision for a user request."""

    route: ResearchRoute
    reason: str = Field(min_length=1, max_length=300)
