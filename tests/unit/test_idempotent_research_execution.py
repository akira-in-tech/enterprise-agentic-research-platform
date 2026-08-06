import asyncio
from collections.abc import Sequence
from uuid import UUID, uuid4

import pytest

from app.schemas.idempotency import ResearchIdempotencyRecord
from app.schemas.research import CreateResearchRunResponse
from app.services.cache import (
    CacheUnavailableError,
    ResearchIdempotencyLockLease,
    create_research_request_fingerprint,
)
from app.services.research.execution import ResearchExecutionResult
from app.services.research.idempotency import (
    IdempotentResearchExecutionService,
    ResearchIdempotencyConflictError,
    ResearchIdempotencyInProgressError,
    ResearchIdempotencyUnavailableError,
)
from app.workflow.state import ResearchState


class RecordingExecutor:
    def __init__(
        self,
        result: ResearchExecutionResult,
        *,
        execution_error: RuntimeError | None = None,
    ) -> None:
        self.result = result
        self.execution_error = execution_error
        self.calls: list[dict[str, object]] = []

    async def execute(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: str,
        requested_by_user_id: UUID | None = None,
        document_ids: Sequence[str] | None = None,
    ) -> ResearchExecutionResult:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "query": query,
                "llm_provider": llm_provider,
                "requested_by_user_id": requested_by_user_id,
                "document_ids": document_ids,
            }
        )
        if self.execution_error is not None:
            raise self.execution_error

        return self.result


class RecordingIdempotencyStore:
    def __init__(
        self,
        *,
        record: ResearchIdempotencyRecord | None = None,
        get_error: CacheUnavailableError | None = None,
        set_error: CacheUnavailableError | None = None,
        get_results: list[ResearchIdempotencyRecord | None] | None = None,
    ) -> None:
        self.record = record
        self.get_error = get_error
        self.set_error = set_error
        self.get_results = get_results
        self.get_calls: list[tuple[UUID, str]] = []
        self.set_calls: list[
            tuple[
                UUID,
                str,
                ResearchIdempotencyRecord,
            ]
        ] = []

    async def get(
        self,
        *,
        tenant_id: UUID,
        client_key: str,
    ) -> ResearchIdempotencyRecord | None:
        self.get_calls.append(
            (
                tenant_id,
                client_key,
            )
        )

        if self.get_error is not None:
            raise self.get_error

        if self.get_results is not None:
            return self.get_results.pop(0)

        return self.record

    async def set(
        self,
        *,
        tenant_id: UUID,
        client_key: str,
        record: ResearchIdempotencyRecord,
    ) -> None:
        self.set_calls.append(
            (
                tenant_id,
                client_key,
                record,
            )
        )

        if self.set_error is not None:
            raise self.set_error

        self.record = record


class RecordingIdempotencyLockManager:
    def __init__(
        self,
        *,
        acquired: bool = True,
        acquire_error: CacheUnavailableError | None = None,
        release_error: CacheUnavailableError | None = None,
        renewed: bool = True,
        renew_error: CacheUnavailableError | None = None,
    ) -> None:
        self.acquired = acquired
        self.acquire_error = acquire_error
        self.release_error = release_error
        self.renewed = renewed
        self.renew_error = renew_error
        self.acquire_calls: list[tuple[UUID, str]] = []
        self.release_calls: list[ResearchIdempotencyLockLease] = []
        self.renew_calls: list[ResearchIdempotencyLockLease] = []

    async def acquire(
        self,
        *,
        tenant_id: UUID,
        client_key: str,
    ) -> ResearchIdempotencyLockLease | None:
        self.acquire_calls.append(
            (
                tenant_id,
                client_key,
            )
        )

        if self.acquire_error is not None:
            raise self.acquire_error

        if not self.acquired:
            return None

        return ResearchIdempotencyLockLease(
            redis_key="enterprise-research:v1:test-lock",
            owner_token=uuid4().hex,
        )

    async def release(
        self,
        lease: ResearchIdempotencyLockLease,
    ) -> bool:
        self.release_calls.append(
            lease,
        )

        if self.release_error is not None:
            raise self.release_error

        return True

    async def renew(
        self,
        lease: ResearchIdempotencyLockLease,
    ) -> bool:
        self.renew_calls.append(
            lease,
        )

        if self.renew_error is not None:
            raise self.renew_error

        return self.renewed


def create_execution_result() -> ResearchExecutionResult:
    state: ResearchState = {
        "query": "What is a mutex?",
        "status": "direct_answer_completed",
        "route": "direct",
        "answer": "A mutex protects a critical section.",
    }

    return ResearchExecutionResult(
        research_run_id=uuid4(),
        llm_provider="ollama",
        state=state,
    )


@pytest.mark.anyio
async def test_without_idempotency_key_delegates_directly() -> None:
    executor = RecordingExecutor(create_execution_result())
    store = RecordingIdempotencyStore()
    service = IdempotentResearchExecutionService(
        executor,
        store,
        RecordingIdempotencyLockManager(),
    )
    tenant_id = uuid4()

    result = await service.execute(
        tenant_id=tenant_id,
        query="What is a mutex?",
        llm_provider="qwen",
    )

    assert result == executor.result
    assert len(executor.calls) == 1
    assert store.get_calls == []
    assert store.set_calls == []


@pytest.mark.anyio
async def test_idempotency_miss_executes_and_stores_record() -> None:
    executor = RecordingExecutor(create_execution_result())
    store = RecordingIdempotencyStore()
    tenant_id = uuid4()
    user_id = uuid4()

    lock_manager = RecordingIdempotencyLockManager()
    service = IdempotentResearchExecutionService(
        executor,
        store,
        lock_manager,
    )

    result = await service.execute(
        tenant_id=tenant_id,
        requested_by_user_id=user_id,
        query="  What is a mutex?  ",
        llm_provider="qwen",
        idempotency_key="  request-123  ",
    )

    assert result == executor.result
    assert result.idempotency_replayed is False
    assert len(executor.calls) == 1
    assert store.get_calls == [
        (
            tenant_id,
            "request-123",
        ),
        (
            tenant_id,
            "request-123",
        ),
    ]
    assert lock_manager.acquire_calls == [
        (
            tenant_id,
            "request-123",
        )
    ]
    assert len(lock_manager.release_calls) == 1
    assert len(store.set_calls) == 1

    stored_tenant, stored_key, stored_record = store.set_calls[0]

    assert stored_tenant == tenant_id
    assert stored_key == "request-123"
    assert stored_record.request_fingerprint == (
        create_research_request_fingerprint(
            query="What is a mutex?",
            llm_provider="ollama",
            requested_by_user_id=user_id,
        )
    )
    assert stored_record.response.research_run_id == result.research_run_id


@pytest.mark.anyio
async def test_matching_idempotency_record_replays_without_execution() -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    original_result = create_execution_result()
    record = ResearchIdempotencyRecord(
        request_fingerprint=(
            create_research_request_fingerprint(
                query="What is a mutex?",
                llm_provider="ollama",
                requested_by_user_id=user_id,
            )
        ),
        response=CreateResearchRunResponse(
            research_run_id=original_result.research_run_id,
            llm_provider="ollama",
            status="completed",
            cache_hit=False,
            workflow_status="direct_answer_completed",
            route="direct",
            answer="A mutex protects a critical section.",
        ),
    )
    executor = RecordingExecutor(create_execution_result())
    store = RecordingIdempotencyStore(
        record=record,
    )
    service = IdempotentResearchExecutionService(
        executor,
        store,
        RecordingIdempotencyLockManager(),
    )

    result = await service.execute(
        tenant_id=tenant_id,
        requested_by_user_id=user_id,
        query="What is a mutex?",
        llm_provider="qwen",
        idempotency_key="request-123",
    )

    assert result.research_run_id == (original_result.research_run_id)
    assert result.idempotency_replayed is True
    assert result.state["answer"] == ("A mutex protects a critical section.")
    assert executor.calls == []
    assert store.set_calls == []


@pytest.mark.anyio
async def test_reused_key_with_different_request_conflicts() -> None:
    record = ResearchIdempotencyRecord(
        request_fingerprint=(
            create_research_request_fingerprint(
                query="What is a mutex?",
                llm_provider="ollama",
                requested_by_user_id=None,
            )
        ),
        response=CreateResearchRunResponse(
            research_run_id=uuid4(),
            llm_provider="ollama",
            status="completed",
            cache_hit=False,
            workflow_status="direct_answer_completed",
            route="direct",
            answer="A mutex protects a critical section.",
        ),
    )
    executor = RecordingExecutor(create_execution_result())
    store = RecordingIdempotencyStore(
        record=record,
    )
    service = IdempotentResearchExecutionService(
        executor,
        store,
        RecordingIdempotencyLockManager(),
    )

    with pytest.raises(
        ResearchIdempotencyConflictError,
        match="different research request",
    ):
        await service.execute(
            tenant_id=uuid4(),
            query="Explain Linux epoll.",
            llm_provider="qwen",
            idempotency_key="request-123",
        )

    assert executor.calls == []
    assert store.set_calls == []


@pytest.mark.anyio
async def test_idempotency_lookup_failure_is_fail_closed() -> None:
    executor = RecordingExecutor(create_execution_result())
    store = RecordingIdempotencyStore(
        get_error=CacheUnavailableError("Redis is unavailable."),
    )
    service = IdempotentResearchExecutionService(
        executor,
        store,
        RecordingIdempotencyLockManager(),
    )

    with pytest.raises(
        ResearchIdempotencyUnavailableError,
        match="store is unavailable",
    ):
        await service.execute(
            tenant_id=uuid4(),
            query="What is a mutex?",
            llm_provider="qwen",
            idempotency_key="request-123",
        )

    assert executor.calls == []


@pytest.mark.anyio
async def test_held_lock_rejects_duplicate_execution() -> None:
    executor = RecordingExecutor(create_execution_result())
    store = RecordingIdempotencyStore()
    lock_manager = RecordingIdempotencyLockManager(
        acquired=False,
    )
    service = IdempotentResearchExecutionService(
        executor,
        store,
        lock_manager,
    )

    with pytest.raises(
        ResearchIdempotencyInProgressError,
        match="already in progress",
    ):
        await service.execute(
            tenant_id=uuid4(),
            query="What is a mutex?",
            llm_provider="qwen",
            idempotency_key="request-123",
        )

    assert executor.calls == []
    assert store.set_calls == []
    assert lock_manager.release_calls == []


@pytest.mark.anyio
async def test_lock_acquisition_failure_is_fail_closed() -> None:
    executor = RecordingExecutor(create_execution_result())
    store = RecordingIdempotencyStore()
    lock_manager = RecordingIdempotencyLockManager(
        acquire_error=CacheUnavailableError("Redis is unavailable."),
    )
    service = IdempotentResearchExecutionService(
        executor,
        store,
        lock_manager,
    )

    with pytest.raises(
        ResearchIdempotencyUnavailableError,
        match="lock is unavailable",
    ):
        await service.execute(
            tenant_id=uuid4(),
            query="What is a mutex?",
            llm_provider="qwen",
            idempotency_key="request-123",
        )

    assert executor.calls == []
    assert store.set_calls == []


@pytest.mark.anyio
async def test_record_created_before_lock_double_check_is_replayed() -> None:
    tenant_id = uuid4()
    original_result = create_execution_result()
    record = ResearchIdempotencyRecord(
        request_fingerprint=(
            create_research_request_fingerprint(
                query="What is a mutex?",
                llm_provider="ollama",
                requested_by_user_id=None,
            )
        ),
        response=CreateResearchRunResponse(
            research_run_id=original_result.research_run_id,
            llm_provider="ollama",
            status="completed",
            cache_hit=False,
            workflow_status="direct_answer_completed",
            route="direct",
            answer="A mutex protects a critical section.",
        ),
    )
    executor = RecordingExecutor(create_execution_result())
    store = RecordingIdempotencyStore(
        get_results=[
            None,
            record,
        ],
    )
    lock_manager = RecordingIdempotencyLockManager()
    service = IdempotentResearchExecutionService(
        executor,
        store,
        lock_manager,
    )

    result = await service.execute(
        tenant_id=tenant_id,
        query="What is a mutex?",
        llm_provider="qwen",
        idempotency_key="request-123",
    )

    assert result.research_run_id == original_result.research_run_id
    assert result.idempotency_replayed is True
    assert executor.calls == []
    assert store.set_calls == []
    assert len(store.get_calls) == 2
    assert len(lock_manager.acquire_calls) == 1
    assert len(lock_manager.release_calls) == 1


@pytest.mark.anyio
async def test_executor_failure_still_releases_lock() -> None:
    executor = RecordingExecutor(
        create_execution_result(),
        execution_error=RuntimeError("Workflow failed."),
    )
    store = RecordingIdempotencyStore()
    lock_manager = RecordingIdempotencyLockManager()
    service = IdempotentResearchExecutionService(
        executor,
        store,
        lock_manager,
    )

    with pytest.raises(
        RuntimeError,
        match="Workflow failed",
    ):
        await service.execute(
            tenant_id=uuid4(),
            query="What is a mutex?",
            llm_provider="qwen",
            idempotency_key="request-123",
        )

    assert len(executor.calls) == 1
    assert store.set_calls == []
    assert len(lock_manager.acquire_calls) == 1
    assert len(lock_manager.release_calls) == 1


class SlowExecutor:
    """Execute for long enough that a short renew interval fires at least once."""

    def __init__(
        self,
        result: ResearchExecutionResult,
        *,
        delay_seconds: float = 0.05,
    ) -> None:
        self.result = result
        self.delay_seconds = delay_seconds
        self.cancelled = False

    async def execute(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: str,
        requested_by_user_id: UUID | None = None,
        document_ids: Sequence[str] | None = None,
    ) -> ResearchExecutionResult:
        try:
            await asyncio.sleep(self.delay_seconds)
        except asyncio.CancelledError:
            self.cancelled = True
            raise

        return self.result


@pytest.mark.anyio
async def test_execute_renews_the_lock_during_a_long_running_execution() -> None:
    executor = SlowExecutor(create_execution_result(), delay_seconds=0.05)
    store = RecordingIdempotencyStore()
    lock_manager = RecordingIdempotencyLockManager()
    service = IdempotentResearchExecutionService(
        executor,
        store,
        lock_manager,
        renew_interval_seconds=0.01,
    )

    result = await service.execute(
        tenant_id=uuid4(),
        query="Compare HTTP/2 and HTTP/3.",
        llm_provider="qwen",
        idempotency_key="request-123",
    )

    assert result is executor.result
    assert len(lock_manager.renew_calls) >= 1
    assert len(lock_manager.release_calls) == 1


@pytest.mark.anyio
async def test_execute_cancels_the_execution_when_the_lease_is_lost() -> None:
    executor = SlowExecutor(create_execution_result(), delay_seconds=1.0)
    store = RecordingIdempotencyStore()
    lock_manager = RecordingIdempotencyLockManager(renewed=False)
    service = IdempotentResearchExecutionService(
        executor,
        store,
        lock_manager,
        renew_interval_seconds=0.01,
    )

    with pytest.raises(asyncio.CancelledError):
        await service.execute(
            tenant_id=uuid4(),
            query="Compare HTTP/2 and HTTP/3.",
            llm_provider="qwen",
            idempotency_key="request-123",
        )

    assert executor.cancelled is True
    # The lease was already lost, so no completed record was ever written --
    # avoiding a race with whatever process now holds the lock.
    assert store.set_calls == []
