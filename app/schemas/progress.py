from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ResearchProgressStatus = Literal[
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
]


class ResearchProgressRecord(BaseModel):
    """Represent the latest observable lifecycle state of one research run."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
    )

    research_run_id: UUID
    status: ResearchProgressStatus
    message: str = Field(
        min_length=1,
        max_length=300,
    )
    updated_at: datetime
    workflow_status: str | None = None
    error_message: str | None = None
