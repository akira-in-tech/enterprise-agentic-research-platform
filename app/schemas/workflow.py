from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ResearchAgentRole = Literal[
    "intent_router",
    "planner",
    "web_scout",
    "local_scout",
    "evidence_judge",
    "analyst",
    "reflect",
    "writer",
]

EvidenceSourcePreference = Literal[
    "web",
    "private",
    "hybrid",
]


class EvidenceGap(BaseModel):
    """Represent one evidence gap identified during research."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    topic: str = Field(min_length=3, max_length=300)
    reason: str = Field(min_length=3, max_length=500)
    source_preference: EvidenceSourcePreference = "hybrid"


class EvidenceConflict(BaseModel):
    """Represent a disagreement between two or more evidence sources."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    claim: str = Field(min_length=3, max_length=500)
    source_ids: list[str] = Field(min_length=2, max_length=20)
    explanation: str = Field(min_length=3, max_length=1_000)


class ResearchFinding(BaseModel):
    """Represent one evidence-backed conclusion produced by the analyst."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    claim: str = Field(min_length=3, max_length=2_000)
    confidence: Literal["high", "medium", "low"]
    source_ids: list[str] = Field(min_length=1, max_length=20)


class SupplementaryResearchQuery(BaseModel):
    """Represent a focused follow-up query produced by the reflect agent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(min_length=3, max_length=300)
    source_preference: EvidenceSourcePreference
    reason: str = Field(min_length=3, max_length=500)
