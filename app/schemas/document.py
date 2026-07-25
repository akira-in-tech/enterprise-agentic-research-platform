from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

DocumentMediaType = Literal[
    "text/plain",
    "text/markdown",
]


class PrivateDocument(BaseModel):
    """Represent one validated private document."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    document_id: str = Field(
        pattern=r"^DOC-[0-9A-F]{16}$",
    )

    tenant_id: str = Field(
        min_length=1,
        max_length=100,
    )

    filename: str = Field(
        min_length=1,
        max_length=255,
    )

    media_type: DocumentMediaType

    content: str = Field(
        min_length=1,
        max_length=2_000_000,
    )

    content_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
    )


class DocumentChunk(BaseModel):
    """Represent one deterministic document chunk."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    chunk_id: str = Field(
        pattern=r"^CHK-[0-9A-F]{16}$",
    )

    document_id: str = Field(
        pattern=r"^DOC-[0-9A-F]{16}$",
    )

    tenant_id: str = Field(
        min_length=1,
        max_length=100,
    )

    position: int = Field(
        ge=0,
    )

    word_start: int = Field(
        ge=0,
    )

    word_end: int = Field(
        ge=1,
    )

    content: str = Field(
        min_length=1,
        max_length=20_000,
    )

    @model_validator(mode="after")
    def validate_word_range(self) -> Self:
        """Require an increasing half-open word range."""

        if self.word_end <= self.word_start:
            raise ValueError(
                "word_end must be greater than word_start."
            )

        return self