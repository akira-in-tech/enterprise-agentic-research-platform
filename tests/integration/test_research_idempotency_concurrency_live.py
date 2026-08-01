import asyncio
from uuid import UUID, uuid4

import pytest

from app.core.config import settings
from app.services.cache import (
    RedisConnection,
    RedisResearchIdempotencyLockManager,
    RedisResearchIdempotencyStore,
    create_research_idempotency_lock_redis_key,
    create_research_idempotency_redis_key,
)
from app.services.research.execution import ResearchExecutionResult
from app.services.research.idempotency import (
    IdempotentResearchExecutionService,
    ResearchIdempotencyInProgressError,
)
from app.workflow.state import ResearchState


class BlockingResearchExecutor:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.continue_execution = asyncio.Event()
        self.calls = 0

    async def execute(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: str,
        requested_by_user_id: UUID | None = None,
    ) -> ResearchExecutionResult:
        del tenant_id
        del llm_provider
        del requested_by_user_id

        self.calls += 1
        self.started.set()

        await self.continue_execution.wait()

        state: ResearchState = {
            "query": query,
            "status": "direct_answer_completed",
            "route": "direct",
            "answer": "A mutex protects a critical section.",
        }

        return ResearchExecutionResult(
            research_run_id=uuid4(),
            llm_provider="ollama",
            state=state,
        )


@pytest.mark.integration
@pytest.mark.anyio
async def test_live_redis_allows_only_one_idempotent_execution() -> None:
    """Verify concurrent requests execute once and later replay."""

    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    connection = RedisConnection.from_url()
    store = RedisResearchIdempotencyStore(
        connection,
        ttl_seconds=60,
    )
    lock_manager = RedisResearchIdempotencyLockManager(
        connection,
        ttl_seconds=60,
    )
    executor = BlockingResearchExecutor()
    service = IdempotentResearchExecutionService(
        executor,
        store,
        lock_manager,
    )
    tenant_id = uuid4()
    client_key = "live-concurrent-request"
    query = "What is a mutex?"
    record_key = create_research_idempotency_redis_key(
        tenant_id=tenant_id,
        client_key=client_key,
    )
    lock_key = create_research_idempotency_lock_redis_key(
        tenant_id=tenant_id,
        client_key=client_key,
    )
    first_task: asyncio.Task[ResearchExecutionResult] | None = None

    try:
        await connection.delete(
            key=record_key,
        )
        await connection.delete(
            key=lock_key,
        )

        first_task = asyncio.create_task(
            service.execute(
                tenant_id=tenant_id,
                query=query,
                llm_provider="qwen",
                idempotency_key=client_key,
            )
        )

        await asyncio.wait_for(
            executor.started.wait(),
            timeout=2,
        )

        with pytest.raises(
            ResearchIdempotencyInProgressError,
            match="already in progress",
        ):
            await asyncio.wait_for(
                service.execute(
                    tenant_id=tenant_id,
                    query=query,
                    llm_provider="qwen",
                    idempotency_key=client_key,
                ),
                timeout=2,
            )

        assert executor.calls == 1

        executor.continue_execution.set()

        first_result = await asyncio.wait_for(
            first_task,
            timeout=2,
        )
        replayed_result = await service.execute(
            tenant_id=tenant_id,
            query=query,
            llm_provider="qwen",
            idempotency_key=client_key,
        )

        assert executor.calls == 1
        assert replayed_result.research_run_id == first_result.research_run_id
        assert replayed_result.idempotency_replayed is True
        assert (
            await connection.get_text(
                key=lock_key,
            )
            is None
        )

    finally:
        executor.continue_execution.set()

        if first_task is not None:
            await asyncio.gather(
                first_task,
                return_exceptions=True,
            )

        try:
            await connection.delete(
                key=record_key,
            )
            await connection.delete(
                key=lock_key,
            )
        finally:
            await connection.close()
