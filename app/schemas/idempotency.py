from pydantic import BaseModel, ConfigDict, Field

from app.schemas.research import CreateResearchRunResponse


class ResearchIdempotencyRecord(BaseModel):
    """Store one completed response for safe request replay."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    request_fingerprint: str = Field(
        pattern=r"^[0-9a-f]{64}$",
    )
    response: CreateResearchRunResponse
