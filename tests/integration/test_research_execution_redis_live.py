from uuid import UUID, uuid4

import pytest

from app.core.config import settings
from app.services.cache import (
    RedisConnection,
    RedisResearchResultCache,
    create_research_result_cache_key,
)
from app.services.llm.factory import CanonicalLLMProvider
from app.services.research.execution import ResearchExecutionService
from app.workflow.state import ResearchState


class RecordingResearchRunStore:
    """Record lifecycle calls without requiring PostgreSQL."""

    def __init__(self) -> None:
        self.events: list[str] = []
        self.research_run_ids: list[UUID] = []

    async def create_queued(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: CanonicalLLMProvider,
        requested_by_user_id: UUID | None,
        research_run_id: UUID | None = None,
    ) -> UUID:
        research_run_id = research_run_id or uuid4()
        self.research_run_ids.append(
            research_run_id,
        )
        self.events.append("queued")

        return research_run_id

    async def mark_running(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> None:
        assert research_run_id in self.research_run_ids
        self.events.append("running")

    async def mark_completed(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        result: ResearchState | None = None,
    ) -> None:
        assert research_run_id in self.research_run_ids
        self.events.append("completed")

    async def mark_failed(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        error_message: str,
    ) -> None:
        assert research_run_id in self.research_run_ids
        self.events.append("failed")


class RecordingWorkflow:
    """Return one deterministic result and count real executions."""

    def __init__(
        self,
        result: ResearchState,
    ) -> None:
        self._result = result
        self.inputs: list[ResearchState] = []
        self.close_calls = 0

    async def ainvoke(
        self,
        state: ResearchState,
    ) -> ResearchState:
        self.inputs.append(state)

        return self._result

    async def close(self) -> None:
        self.close_calls += 1


@pytest.mark.integration
@pytest.mark.anyio
async def test_research_execution_redis_miss_then_hit() -> None:
    """Verify execution writes and reuses a real Redis cache entry."""

    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    connection = RedisConnection.from_url()
    cache = RedisResearchResultCache(
        connection,
        ttl_seconds=60,
    )
    store = RecordingResearchRunStore()
    tenant_id = uuid4()
    query = "Explain HTTP keep-alive."
    cache_key = create_research_result_cache_key(
        tenant_id=tenant_id,
        llm_provider="ollama",
        query=query,
    )
    workflow_result: ResearchState = {
        "query": query,
        "status": "direct_answer_completed",
        "route": "direct",
        "route_reason": "The question uses stable engineering knowledge.",
        "answer": ("HTTP keep-alive allows multiple requests to reuse one transport connection."),
    }
    workflow = RecordingWorkflow(
        workflow_result,
    )
    workflow_factory_calls: list[CanonicalLLMProvider] = []

    def create_workflow(
        provider: CanonicalLLMProvider,
    ) -> RecordingWorkflow:
        workflow_factory_calls.append(provider)

        return workflow

    service = ResearchExecutionService(
        store,
        create_workflow,
        result_cache=cache,
    )

    try:
        await connection.delete(
            key=cache_key,
        )

        first_result = await service.execute(
            tenant_id=tenant_id,
            query=query,
            llm_provider="qwen",
        )
        second_result = await service.execute(
            tenant_id=tenant_id,
            query=query,
            llm_provider="qwen",
        )

        assert first_result.cache_hit is False
        assert second_result.cache_hit is True

        assert first_result.state == workflow_result
        assert second_result.state == workflow_result

        assert first_result.research_run_id != (second_result.research_run_id)

        assert workflow_factory_calls == [
            "ollama",
        ]
        assert workflow.inputs == [
            {
                "query": query,
            }
        ]
        assert workflow.close_calls == 1

        assert store.events == [
            "queued",
            "running",
            "completed",
            "queued",
            "running",
            "completed",
        ]

        remaining_ttl = await connection.ttl_seconds(
            key=cache_key,
        )

        assert 0 < remaining_ttl <= 60

    finally:
        try:
            await connection.delete(
                key=cache_key,
            )
        finally:
            await connection.close()
