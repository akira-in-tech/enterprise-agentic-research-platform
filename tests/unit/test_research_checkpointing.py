from collections.abc import Awaitable, Callable

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import SecretStr

from app.schemas.intent import IntentDecision
from app.schemas.planner import ResearchPlan
from app.services.research.checkpointing import create_langgraph_postgres_url
from app.services.research.execution import LangGraphResearchWorkflow
from app.workflow.graph import build_research_graph
from app.workflow.state import ResearchState


def test_checkpoint_url_converts_asyncpg_driver_without_hiding_password() -> None:
    result = create_langgraph_postgres_url(
        SecretStr("postgresql+asyncpg://research_user:secret@db:5432/research")
    )

    assert result == "postgresql://research_user:secret@db:5432/research"


def test_checkpoint_url_translates_asyncpg_ssl_param_to_psycopg_sslmode() -> None:
    # entrypoint.build_managed_database_url appends ?ssl=require for the
    # managed RDS path -- asyncpg accepts that key, but raw psycopg/libpq
    # rejects it outright ("invalid URI query parameter: ssl") and expects
    # sslmode instead. This crashed every staging container's startup
    # lifespan before the key rename was added.
    result = create_langgraph_postgres_url(
        SecretStr("postgresql+asyncpg://research_user:secret@db:5432/research?ssl=require")
    )

    assert result == "postgresql://research_user:secret@db:5432/research?sslmode=require"


def test_checkpoint_url_rejects_non_postgresql_database() -> None:
    with pytest.raises(ValueError, match="require a PostgreSQL"):
        create_langgraph_postgres_url(SecretStr("sqlite+aiosqlite:///test.db"))


@pytest.mark.anyio
async def test_langgraph_workflow_resumes_after_last_successful_node() -> None:
    classifier_calls = 0
    answer_calls = 0

    async def classify(_: str) -> IntentDecision:
        nonlocal classifier_calls
        classifier_calls += 1
        return IntentDecision(route="direct", reason="Stable question.")

    async def answer(_: str) -> str:
        nonlocal answer_calls
        answer_calls += 1
        if answer_calls == 1:
            raise RuntimeError("transient provider failure")
        return "Recovered answer."

    async def unused_plan(_: str) -> ResearchPlan:
        raise AssertionError("planner should not execute")

    async def unused_search(_: ResearchPlan) -> list[object]:
        raise AssertionError("search should not execute")

    checkpointer = InMemorySaver()
    graph = build_research_graph(
        classify,
        unused_plan,
        answer,
        unused_search,  # type: ignore[arg-type]
        checkpointer=checkpointer,
    )
    close_callback: Callable[[], Awaitable[None]]

    async def close() -> None:
        return None

    close_callback = close
    first = LangGraphResearchWorkflow(graph, close_callback)
    first.configure_durable_execution(thread_id="tenant:run", resume=False)

    with pytest.raises(RuntimeError, match="transient provider failure"):
        await first.ainvoke({"query": "Explain epoll."})

    resumed = LangGraphResearchWorkflow(graph, close_callback)
    resumed.configure_durable_execution(thread_id="tenant:run", resume=True)
    result: ResearchState = await resumed.ainvoke({"query": "ignored on resume"})

    assert result["answer"] == "Recovered answer."
    assert classifier_calls == 1
    assert answer_calls == 2
