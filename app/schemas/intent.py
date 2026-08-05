from typing import Literal

from pydantic import BaseModel, Field

ResearchRoute = Literal["direct", "deep_research"]


class IntentDecision(BaseModel):
    """Represent the routing decision for a user request."""

    route: ResearchRoute
    reason: str = Field(min_length=1, max_length=300)
    is_high_risk_domain: bool = Field(
        default=False,
        description=(
            "True when the request touches a medical, legal, financial, or "
            "safety/security domain where conclusions must not be presented "
            "as an unqualified final decision without human review."
        ),
    )
