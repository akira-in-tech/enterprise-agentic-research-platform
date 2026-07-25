import pytest

from app.schemas.intent import IntentDecision
from app.schemas.planner import (
    ReportSection,
    ResearchPlan,
    ResearchTask,
)
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


async def fake_direct_answer(query: str) -> str:
    return f"Direct answer for: {query}"


async def fake_plan_creator(_: str) -> ResearchPlan:
    return ResearchPlan(
        goal="Compare HTTP/2 and HTTP/3.",
        sub_questions=[
            "How do HTTP/2 and HTTP/3 differ architecturally?",
            "What security and reliability trade-offs do they have?",
        ],
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
        report_outline=[
            ReportSection(
                title="Technical Background",
                purpose="Explain the foundations of both protocols.",
            ),
            ReportSection(
                title="Architecture",
                purpose="Compare their transport and connection models.",
            ),
            ReportSection(
                title="Trade-offs",
                purpose="Evaluate reliability, security, and performance.",
            ),
        ],
    )


@pytest.mark.anyio
async def test_research_graph_generates_direct_answer() -> None:
    graph = build_research_graph(
        fake_direct_classifier,
        fake_plan_creator,
        fake_direct_answer,
    )

    result = await graph.ainvoke(
        {
            "query": "Explain idempotency in REST APIs.",
            "status": "pending",
        }
    )

    assert result["route"] == "direct"
    assert result["status"] == "direct_answer_completed"
    assert result["answer"] == (
        "Direct answer for: Explain idempotency in REST APIs."
    )
    assert "plan" not in result


@pytest.mark.anyio
async def test_research_graph_creates_plan_for_deep_research() -> None:
    graph = build_research_graph(
        fake_research_classifier,
        fake_plan_creator,
        fake_direct_answer,
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
    assert "answer" not in result
    assert len(result["plan"].sub_questions) == 2
    assert len(result["plan"].report_outline) == 3