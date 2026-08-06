from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_step import ResearchAgentStep
from app.db.repositories import ResearchAgentStepRepository


def create_session_mock() -> tuple[AsyncSession, AsyncMock]:
    session_mock = AsyncMock(spec=AsyncSession)

    return cast(AsyncSession, session_mock), session_mock


@pytest.mark.anyio
async def test_append_persists_a_step_without_committing() -> None:
    session, session_mock = create_session_mock()
    repository = ResearchAgentStepRepository(session)
    tenant_id = uuid4()
    research_run_id = uuid4()

    step = await repository.append(
        tenant_id=tenant_id,
        research_run_id=research_run_id,
        sequence=0,
        agent_role="intent_router",
        status="completed",
        summary="Routed to deep_research.",
    )

    assert step.tenant_id == tenant_id
    assert step.research_run_id == research_run_id
    assert step.agent_role == "intent_router"
    assert step.status == "completed"
    session_mock.add.assert_called_once_with(step)
    session_mock.flush.assert_awaited_once_with()
    session_mock.commit.assert_not_awaited()


@pytest.mark.anyio
async def test_append_strips_blank_summary_to_none() -> None:
    session, _ = create_session_mock()
    repository = ResearchAgentStepRepository(session)

    step = await repository.append(
        tenant_id=uuid4(),
        research_run_id=uuid4(),
        sequence=1,
        agent_role="planner",
        status="started",
        summary="   ",
    )

    assert step.summary is None


@pytest.mark.anyio
async def test_append_rejects_negative_sequence() -> None:
    session, _ = create_session_mock()
    repository = ResearchAgentStepRepository(session)

    with pytest.raises(ValueError, match="sequence must not be negative"):
        await repository.append(
            tenant_id=uuid4(),
            research_run_id=uuid4(),
            sequence=-1,
            agent_role="planner",
            status="started",
        )


@pytest.mark.anyio
async def test_append_rejects_invalid_status() -> None:
    session, _ = create_session_mock()
    repository = ResearchAgentStepRepository(session)

    with pytest.raises(ValueError, match="status must be"):
        await repository.append(
            tenant_id=uuid4(),
            research_run_id=uuid4(),
            sequence=0,
            agent_role="planner",
            status="done",
        )


@pytest.mark.anyio
async def test_list_for_run_returns_steps_in_recorded_order() -> None:
    session, session_mock = create_session_mock()
    tenant_id = uuid4()
    research_run_id = uuid4()
    steps = [
        ResearchAgentStep(
            tenant_id=tenant_id,
            research_run_id=research_run_id,
            sequence=index,
            agent_role="planner",
            status="completed",
        )
        for index in range(3)
    ]
    session_mock.scalars.return_value = steps

    repository = ResearchAgentStepRepository(session)
    result = await repository.list_for_run(
        tenant_id=tenant_id,
        research_run_id=research_run_id,
    )

    assert result == steps
