from pydantic import BaseModel, ConfigDict, Field


class WebSource(BaseModel):
    """Represent one canonical public web source."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    source_id: str = Field(
        pattern=r"^WEB-[0-9A-F]{16}$",
    )

    title: str = Field(
        min_length=1,
        max_length=500,
    )

    url: str = Field(
        min_length=8,
        max_length=2048,
    )

    content: str = Field(
        max_length=20_000,
    )

    provider: str = Field(
        min_length=1,
        max_length=50,
    )