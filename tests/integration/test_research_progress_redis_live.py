import asyncio
from uuid import UUID, uuid4

import pytest

from app.core.config import settings
from app.services.cache import RedisConnection, RedisResearchProgressStore
from app.services.llm.factory import CanonicalLLMProvider
from app.services.research.execution import ResearchExecutionService
from app.workflow.state import ResearchState

pytestmark = pytest.mark.integration


class LiveResearchRunStore:
    def __init__(self) -> None:
        self.research_run_id = uuid4()

    async def create_queued(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: CanonicalLLMProvider,
        requested_by_user_id: UUID | None,
        research_run_id: UUID | None = None,
    ) -> UUID:
        if research_run_id is not None:
            self.research_run_id = research_run_id
        return self.research_run_id

    async def mark_running(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> None:
        return None

    async def mark_completed(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        result: ResearchState | None = None,
    ) -> None:
        return None

    async def mark_failed(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        error_message: str,
    ) -> None:
        return None


class BlockingWorkflow:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def ainvoke(self, state: ResearchState) -> ResearchState:
        self.started.set()
        await self.release.wait()

        return {
            **state,
            "status": "direct_answer_completed",
            "answer": "epoll observes file descriptors.",
        }

    async def close(self) -> None:
        return None


@pytest.mark.anyio
async def test_live_execution_publishes_running_and_completed_progress() -> None:
    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    connection = RedisConnection.from_url()
    progress_store = RedisResearchProgressStore(connection, ttl_seconds=60)
    research_store = LiveResearchRunStore()
    workflow = BlockingWorkflow()
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    service = ResearchExecutionService(
        research_store,
        lambda _: workflow,
        progress_store=progress_store,
    )

    try:
        execution = asyncio.create_task(
            service.execute(
                tenant_id=tenant_id,
                query="Explain Linux epoll.",
                llm_provider="qwen",
            )
        )
        await asyncio.wait_for(workflow.started.wait(), timeout=2)

        running = await progress_store.get(
            tenant_id=tenant_id,
            research_run_id=research_store.research_run_id,
        )
        isolated = await progress_store.get(
            tenant_id=other_tenant_id,
            research_run_id=research_store.research_run_id,
        )

        assert running is not None
        assert running.status == "running"
        assert isolated is None

        workflow.release.set()
        result = await asyncio.wait_for(execution, timeout=2)
        completed = await progress_store.get(
            tenant_id=tenant_id,
            research_run_id=research_store.research_run_id,
        )

        assert result.research_run_id == research_store.research_run_id
        assert completed is not None
        assert completed.status == "completed"
        assert completed.workflow_status == "direct_answer_completed"
    finally:
        workflow.release.set()
        await progress_store.delete(
            tenant_id=tenant_id,
            research_run_id=research_store.research_run_id,
        )
        await connection.close()
