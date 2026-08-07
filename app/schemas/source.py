from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.document import DocumentMediaType


class WebSource(BaseModel):
    """Represent one canonical public web source."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    source_id: str = Field(
        pattern=r"^(WEB|PAPER)-[0-9A-F]{16}$",
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

    source_type: Literal["web", "paper"] = "web"

    authors: list[str] = Field(
        default_factory=list,
        max_length=20,
    )

    year: int | None = Field(
        default=None,
        ge=1000,
        le=2100,
    )

    venue: str | None = Field(
        default=None,
        max_length=300,
    )


class PrivateSource(BaseModel):
    """Represent one canonical private knowledge source."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    source_id: str = Field(
        pattern=r"^PRIVATE-[0-9A-F]{16}$",
    )

    document_id: str = Field(
        pattern=r"^DOC-[0-9A-F]{16}$",
    )

    chunk_id: str = Field(
        pattern=r"^CHK-[0-9A-F]{16}$",
    )

    filename: str = Field(
        min_length=1,
        max_length=255,
    )

    media_type: DocumentMediaType

    content: str = Field(
        min_length=1,
        max_length=20_000,
    )

    score: float = Field(
        ge=-1.0,
        le=1.0,
    )

    provider: Literal["private_knowledge"] = "private_knowledge"
