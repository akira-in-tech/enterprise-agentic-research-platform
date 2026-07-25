import pytest

from app.schemas.intent import IntentDecision
from app.workflow.graph import build_research_graph


async def fake_direct_classifier(_: str) -> IntentDecision:
    return IntentDecision(
        route="direct",
        reason="The request uses stable technical knowledge.",
    )


async def fake_research_classifier(_: str) -> IntentDecision:
    return IntentDecision(
        route="deep_research",
        reason="The request requires current sources and comparison.",
    )


@pytest.mark.anyio
async def test_research_graph_routes_stable_question_to_direct_answer() -> None:
    graph = build_research_graph(fake_direct_classifier)

    result = await graph.ainvoke(
        {
            "query": "Explain idempotency in REST APIs.",
            "status": "pending",
        }
    )

    assert result["route"] == "direct"
    assert result["route_reason"] == (
        "The request uses stable technical knowledge."
    )
    assert result["status"] == "direct_answer_ready"


@pytest.mark.anyio
async def test_research_graph_routes_protocol_comparison_to_deep_research() -> None:
    graph = build_research_graph(fake_research_classifier)

    result = await graph.ainvoke(
        {
            "query": "Compare HTTP/2 and HTTP/3 using current sources.",
            "status": "pending",
        }
    )

    assert result["route"] == "deep_research"
    assert result["route_reason"] == (
        "The request requires current sources and comparison."
    )
    assert result["status"] == "deep_research_ready"