from unittest.mock import AsyncMock

import pytest

from app.agents.planner import PlannerAgent
from app.schemas.planner import (
    ReportSection,
    ResearchPlan,
    ResearchTask,
)
from app.services.llm.anthropic import AnthropicClient


@pytest.mark.anyio
async def test_planner_returns_structured_research_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm_client = AnthropicClient(
        api_key="test-api-key",
        model="test-model",
    )

    expected_plan = ResearchPlan(
        goal="Compare HTTP/2 and HTTP/3 for production web services.",
        sub_questions=[
            ("How do HTTP/2 and HTTP/3 differ in their transport and connection architecture?"),
            ("How do the protocols behave under latency, packet loss, and connection migration?"),
        ],
        tasks=[
            ResearchTask(
                title="Protocol architecture",
                search_query=("HTTP/2 HTTP/3 protocol architecture differences"),
                rationale=("Establish the transport and protocol design differences."),
            ),
            ResearchTask(
                title="Reliability and performance",
                search_query=("HTTP/2 vs HTTP/3 latency reliability benchmarks"),
                rationale=("Compare behavior under latency and packet loss."),
            ),
        ],
        report_outline=[
            ReportSection(
                title="Technical Background",
                purpose="Explain the foundations of HTTP/2 and HTTP/3.",
            ),
            ReportSection(
                title="Architecture",
                purpose="Compare the transport and connection models.",
            ),
            ReportSection(
                title="Reliability and Performance",
                purpose="Compare behavior under realistic network conditions.",
            ),
            ReportSection(
                title="Recommendations",
                purpose="Identify suitable production use cases.",
            ),
        ],
    )

    generate_structured = AsyncMock(return_value=expected_plan)
    monkeypatch.setattr(
        llm_client,
        "generate_structured",
        generate_structured,
    )

    planner = PlannerAgent(llm_client)

    result = await planner.create_plan("Compare HTTP/2 and HTTP/3 using current technical sources.")

    assert result == expected_plan
    assert len(result.sub_questions) == 2
    assert len(result.tasks) == 2
    assert result.tasks[0].title == "Protocol architecture"
    assert result.report_outline[0].title == "Technical Background"

    generate_structured.assert_awaited_once()


@pytest.mark.anyio
async def test_planner_rejects_empty_query() -> None:
    llm_client = AnthropicClient(
        api_key="test-api-key",
        model="test-model",
    )
    planner = PlannerAgent(llm_client)

    with pytest.raises(ValueError, match="Query must not be empty"):
        await planner.create_plan("   ")
