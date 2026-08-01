from uuid import UUID, uuid4

import pytest

from app.schemas.idempotency import ResearchIdempotencyRecord
from app.schemas.research import CreateResearchRunResponse
from app.services.cache import (
    CacheUnavailableError,
    create_research_request_fingerprint,
)
from app.services.research.execution import ResearchExecutionResult
from app.services.research.idempotency import (
    IdempotentResearchExecutionService,
    ResearchIdempotencyConflictError,
    ResearchIdempotencyUnavailableError,
)
from app.workflow.state import ResearchState


class RecordingExecutor:
    def __init__(
        self,
        result: ResearchExecutionResult,
    ) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    async def execute(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: str,
        requested_by_user_id: UUID | None = None,
    ) -> ResearchExecutionResult:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "query": query,
                "llm_provider": llm_provider,
                "requested_by_user_id": requested_by_user_id,
            }
        )

        return self.result


class RecordingIdempotencyStore:
    def __init__(
        self,
        *,
        record: ResearchIdempotencyRecord | None = None,
        get_error: CacheUnavailableError | None = None,
        set_error: CacheUnavailableError | None = None,
    ) -> None:
        self.record = record
        self.get_error = get_error
        self.set_error = set_error
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
    service = IdempotentResearchExecutionService(
        executor,
        store,
    )
    tenant_id = uuid4()
    user_id = uuid4()

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
        )
    ]
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
