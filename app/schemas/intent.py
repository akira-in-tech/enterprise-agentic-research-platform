from typing import Literal

from pydantic import BaseModel, Field


class IntentDecision(BaseModel):
    """Represent the routing decision for a user request."""

    route: Literal["direct", "deep_research"]
    reason: str = Field(min_length=1, max_length=300)