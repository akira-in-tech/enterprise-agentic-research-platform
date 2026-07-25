from pydantic import BaseModel, Field


class ResearchTask(BaseModel):
    """Represent one executable research task."""

    title: str = Field(min_length=3, max_length=120)

    search_query: str = Field(
        min_length=3,
        max_length=300,
    )

    rationale: str = Field(
        min_length=3,
        max_length=300,
    )


class ResearchPlan(BaseModel):
    """Represent a complete research plan."""

    goal: str = Field(
        min_length=3,
        max_length=300,
    )

    tasks: list[ResearchTask] = Field(
        min_length=1,
        max_length=8,
    )