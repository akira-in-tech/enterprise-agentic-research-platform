import pytest

from app.schemas.intent import IntentDecision
from app.schemas.planner import ResearchPlan, ResearchTask
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


async def fake_plan_creator(_: str) -> ResearchPlan:
    return ResearchPlan(
        goal="Compare HTTP/2 and HTTP/3.",
        tasks=[
            ResearchTask(
                title="Protocol architecture",
                search_query="HTTP/2 HTTP/3 architecture differences",
                rationale="Compare the underlying protocol designs.",
            ),
            ResearchTask(
                title="Security trade-offs",
                search_query="HTTP/2 HTTP/3 security trade-offs",
                rationale="Evaluate protocol security characteristics.",
            ),
        ],
    )


@pytest.mark.anyio
async def test_research_graph_routes_stable_question_to_direct_answer() -> None:
    graph = build_research_graph(
        fake_direct_classifier,
        fake_plan_creator,
    )

    result = await graph.ainvoke(
        {
            "query": "Explain idempotency in REST APIs.",
            "status": "pending",
        }
    )

    assert result["route"] == "direct"
    assert result["status"] == "direct_answer_ready"
    assert "plan" not in result


@pytest.mark.anyio
async def test_research_graph_creates_plan_for_deep_research() -> None:
    graph = build_research_graph(
        fake_research_classifier,
        fake_plan_creator,
    )

    result = await graph.ainvoke(
        {
            "query": "Compare HTTP/2 and HTTP/3 using current sources.",
            "status": "pending",
        }
    )

    assert result["route"] == "deep_research"
    assert result["status"] == "research_plan_ready"
    assert result["plan"].goal == "Compare HTTP/2 and HTTP/3."
    assert len(result["plan"].tasks) == 2