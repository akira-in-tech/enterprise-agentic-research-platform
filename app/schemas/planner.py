from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class ResearchTask(BaseModel):
    """Represent one executable research task."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        min_length=3,
        max_length=120,
    )

    search_query: str = Field(
        min_length=3,
        max_length=300,
    )

    rationale: str = Field(
        min_length=3,
        max_length=300,
    )


class ReportSection(BaseModel):
    """Represent one section in the final research report."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        min_length=3,
        max_length=100,
    )

    purpose: str = Field(
        min_length=3,
        max_length=300,
    )


class ResearchPlan(BaseModel):
    """Represent a complete research plan."""

    model_config = ConfigDict(extra="forbid")

    goal: str = Field(
        min_length=3,
        max_length=300,
    )

    sub_questions: list[
        Annotated[
            str,
            Field(min_length=3, max_length=300),
        ]
    ] = Field(
        min_length=2,
        max_length=6,
    )

    tasks: list[ResearchTask] = Field(
        min_length=2,
        max_length=6,
    )

    report_outline: list[ReportSection] = Field(
        min_length=3,
        max_length=8,
    )
