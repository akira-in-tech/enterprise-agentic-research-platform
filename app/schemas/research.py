from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

UserFacingLLMProvider = Literal[
    "claude",
    "qwen",
]


class CreateResearchRunRequest(BaseModel):
    """Represent a user request to start one research run."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
    )

    query: str = Field(
        min_length=1,
    )
    llm_provider: UserFacingLLMProvider
