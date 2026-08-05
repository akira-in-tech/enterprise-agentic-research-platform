from collections.abc import Awaitable, Callable
from uuid import uuid4

import pytest

from app.core.config import settings
from app.schemas.intent import IntentDecision
from app.schemas.planner import ResearchPlan
from app.services.research.checkpointing import open_langgraph_checkpointer
from app.services.research.execution import LangGraphResearchWorkflow
from app.workflow.graph import build_research_graph
from app.workflow.state import ResearchState

pytestmark = pytest.mark.integration


@pytest.mark.anyio
async def test_langgraph_resumes_from_postgres_node_checkpoint() -> None:
    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    classifier_calls = 0
    answer_calls = 0

    async def classify(_: str) -> IntentDecision:
        nonlocal classifier_calls
        classifier_calls += 1
        return IntentDecision(route="direct", reason="Stable fixture route.")

    async def answer(_: str) -> str:
        nonlocal answer_calls
        answer_calls += 1
        if answer_calls == 1:
            raise RuntimeError("simulated provider interruption")
        return "Resumed from the last successful PostgreSQL checkpoint."

    async def unused_plan(_: str) -> ResearchPlan:
        raise AssertionError("planner should not execute")

    async def unused_search(_: ResearchPlan) -> list[object]:
        raise AssertionError("search should not execute")

    async def close() -> None:
        return None

    close_callback: Callable[[], Awaitable[None]] = close
    thread_id = f"integration:{uuid4()}"

    async with open_langgraph_checkpointer(settings.database_url) as checkpointer:
        graph = build_research_graph(
            classify,
            unused_plan,
            answer,
            unused_search,  # type: ignore[arg-type]
            checkpointer=checkpointer,
        )
        first = LangGraphResearchWorkflow(graph, close_callback)
        first.configure_durable_execution(thread_id=thread_id, resume=False)

        with pytest.raises(RuntimeError, match="simulated provider interruption"):
            await first.ainvoke({"query": "Explain durable checkpoints."})

        resumed = LangGraphResearchWorkflow(graph, close_callback)
        resumed.configure_durable_execution(thread_id=thread_id, resume=True)
        result: ResearchState = await resumed.ainvoke({"query": "ignored"})

        assert result["answer"] == ("Resumed from the last successful PostgreSQL checkpoint.")
        assert classifier_calls == 1
        assert answer_calls == 2
        await checkpointer.adelete_thread(thread_id)
