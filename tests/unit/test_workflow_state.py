from typing import get_args
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.source import PrivateSource
from app.schemas.workflow import (
    EvidenceConflict,
    EvidenceGap,
    ResearchAgentRole,
    ResearchFinding,
    SupplementaryResearchQuery,
)
from app.workflow.state import ResearchState


def test_research_agent_roles_match_the_canonical_eight_agent_charter() -> None:
    assert get_args(ResearchAgentRole) == (
        "intent_router",
        "planner",
        "web_scout",
        "local_scout",
        "evidence_judge",
        "analyst",
        "reflect",
        "writer",
    )


def test_research_state_exposes_the_eight_agent_collaboration_contract() -> None:
    assert ResearchState.__required_keys__ == frozenset({"query"})
    assert {
        "tenant_id",
        "active_agent",
        "private_sources",
        "evidence_gaps",
        "evidence_conflicts",
        "analysis_findings",
        "supplementary_queries",
        "iteration",
        "max_iterations",
        "draft_report",
        "report",
    } <= ResearchState.__optional_keys__


def test_research_state_accepts_typed_collaboration_artifacts() -> None:
    tenant_id = uuid4()
    private_source = PrivateSource(
        source_id="PRIVATE-0123456789ABCDEF",
        document_id="DOC-0123456789ABCDEF",
        chunk_id="CHK-0123456789ABCDEF",
        filename="architecture.md",
        media_type="text/markdown",
        content="The internal architecture requires tenant isolation.",
        score=0.91,
    )
    gap = EvidenceGap(
        topic="Failure recovery",
        reason="The current evidence does not cover recovery semantics.",
        source_preference="private",
    )
    conflict = EvidenceConflict(
        claim="The queue provides exactly-once delivery.",
        source_ids=[
            "WEB-0123456789ABCDEF",
            "PRIVATE-0123456789ABCDEF",
        ],
        explanation="The public and internal sources describe different guarantees.",
    )
    finding = ResearchFinding(
        claim="The system provides at-least-once delivery.",
        confidence="high",
        source_ids=["PRIVATE-0123456789ABCDEF"],
    )
    supplementary_query = SupplementaryResearchQuery(
        query="internal queue failure recovery semantics",
        source_preference="private",
        reason="Resolve the delivery-guarantee conflict.",
    )

    state: ResearchState = {
        "query": "Evaluate the queue architecture.",
        "tenant_id": tenant_id,
        "active_agent": "reflect",
        "private_sources": [private_source],
        "evidence_gaps": [gap],
        "evidence_conflicts": [conflict],
        "analysis_findings": [finding],
        "supplementary_queries": [supplementary_query],
        "iteration": 1,
        "max_iterations": 2,
        "draft_report": "Draft report",
        "report": "Final report",
    }

    assert state["tenant_id"] == tenant_id
    assert state["active_agent"] == "reflect"
    assert state["supplementary_queries"] == [supplementary_query]
    assert state["draft_report"] != state["report"]


def test_evidence_conflict_requires_multiple_sources() -> None:
    with pytest.raises(ValidationError):
        EvidenceConflict(
            claim="Redis guarantees durable storage.",
            source_ids=["WEB-0123456789ABCDEF"],
            explanation="Only one source was supplied.",
        )


def test_research_finding_requires_a_source() -> None:
    with pytest.raises(ValidationError):
        ResearchFinding(
            claim="The architecture is reliable.",
            confidence="medium",
            source_ids=[],
        )


def test_supplementary_query_rejects_unknown_source_preference() -> None:
    with pytest.raises(ValidationError):
        SupplementaryResearchQuery.model_validate(
            {
                "query": "queue recovery semantics",
                "source_preference": "database",
                "reason": "Fill the evidence gap.",
            }
        )
