from unittest.mock import AsyncMock

import pytest

from app.agents.planner import PlannerAgent
from app.schemas.planner import ResearchPlan, ResearchTask
from app.services.claude import ClaudeClient


@pytest.mark.anyio
async def test_planner_returns_structured_research_plan() -> None:
    claude_client = ClaudeClient()

    expected_plan = ResearchPlan(
        goal="Compare HTTP/2 and HTTP/3 for production web services.",
        tasks=[
            ResearchTask(
                title="Protocol architecture",
                search_query=(
                    "HTTP/2 HTTP/3 protocol architecture differences"
                ),
                rationale=(
                    "Establish the transport and protocol design differences."
                ),
            ),
            ResearchTask(
                title="Reliability and performance",
                search_query=(
                    "HTTP/2 vs HTTP/3 latency reliability benchmarks"
                ),
                rationale=(
                    "Compare behavior under latency and packet loss."
                ),
            ),
        ],
    )

    claude_client.generate_structured = AsyncMock(
        return_value=expected_plan
    )

    planner = PlannerAgent(claude_client)

    result = await planner.create_plan(
        "Compare HTTP/2 and HTTP/3 using current technical sources."
    )

    assert result == expected_plan
    assert len(result.tasks) == 2
    assert result.tasks[0].title == "Protocol architecture"

    claude_client.generate_structured.assert_awaited_once()


@pytest.mark.anyio
async def test_planner_rejects_empty_query() -> None:
    claude_client = ClaudeClient()
    planner = PlannerAgent(claude_client)

    with pytest.raises(ValueError, match="Query must not be empty"):
        await planner.create_plan("   ")