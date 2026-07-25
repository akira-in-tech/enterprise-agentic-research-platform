import pytest

from app.schemas.intent import IntentDecision
from app.schemas.planner import (
    ReportSection,
    ResearchPlan,
    ResearchTask,
)
from app.services.search.base import SearchResult
from app.services.search.executor import ResearchTaskResult
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


def create_successful_outcome(
    task: ResearchTask,
    index: int,
) -> ResearchTaskResult:
    return ResearchTaskResult(
        task=task,
        results=[
            SearchResult(
                title=f"Technical source {index}",
                url=f"https://example.com/source-{index}",
                content=f"Evidence for {task.search_query}.",
                source="fake",
            )
        ],
    )


async def fake_successful_search(
    plan: ResearchPlan,
) -> list[ResearchTaskResult]:
    return [
        create_successful_outcome(task, index)
        for index, task in enumerate(plan.tasks, start=1)
    ]


async def fake_partial_search(
    plan: ResearchPlan,
) -> list[ResearchTaskResult]:
    first_task, second_task = plan.tasks

    return [
        create_successful_outcome(first_task, 1),
        ResearchTaskResult(
            task=second_task,
            results=[],
            error="RuntimeError: simulated provider failure.",
        ),
    ]


async def fake_failed_search(
    plan: ResearchPlan,
) -> list[ResearchTaskResult]:
    return [
        ResearchTaskResult(
            task=task,
            results=[],
            error="RuntimeError: simulated provider failure.",
        )
        for task in plan.tasks
    ]


@pytest.mark.anyio
async def test_research_graph_generates_direct_answer() -> None:
    graph = build_research_graph(
        fake_direct_classifier,
        fake_plan_creator,
        fake_direct_answer,
        fake_successful_search,
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
    assert "web_search_results" not in result


@pytest.mark.anyio
async def test_research_graph_searches_for_deep_research() -> None:
    graph = build_research_graph(
        fake_research_classifier,
        fake_plan_creator,
        fake_direct_answer,
        fake_successful_search,
    )

    result = await graph.ainvoke(
        {
            "query": "Compare HTTP/2 and HTTP/3 using current sources.",
            "status": "pending",
        }
    )

    assert result["route"] == "deep_research"
    assert result["status"] == "web_search_completed"
    assert result["plan"].goal == "Compare HTTP/2 and HTTP/3."
    assert len(result["plan"].sub_questions) == 2
    assert len(result["plan"].report_outline) == 3

    outcomes = result["web_search_results"]

    assert len(outcomes) == 2
    assert all(outcome.succeeded for outcome in outcomes)
    assert "answer" not in result


@pytest.mark.anyio
async def test_research_graph_preserves_partial_search_results() -> None:
    graph = build_research_graph(
        fake_research_classifier,
        fake_plan_creator,
        fake_direct_answer,
        fake_partial_search,
    )

    result = await graph.ainvoke(
        {
            "query": "Compare HTTP/2 and HTTP/3 using current sources.",
            "status": "pending",
        }
    )

    assert result["status"] == "web_search_partial"

    outcomes = result["web_search_results"]

    assert outcomes[0].succeeded is True
    assert outcomes[1].succeeded is False
    assert outcomes[1].error == (
        "RuntimeError: simulated provider failure."
    )


@pytest.mark.anyio
async def test_research_graph_marks_total_search_failure() -> None:
    graph = build_research_graph(
        fake_research_classifier,
        fake_plan_creator,
        fake_direct_answer,
        fake_failed_search,
    )

    result = await graph.ainvoke(
        {
            "query": "Compare HTTP/2 and HTTP/3 using current sources.",
            "status": "pending",
        }
    )

    assert result["status"] == "web_search_failed"
    assert all(
        not outcome.succeeded
        for outcome in result["web_search_results"]
    )