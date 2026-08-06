from uuid import UUID, uuid4

import pytest

from app.schemas.cache import CachedResearchResult
from app.schemas.evidence import (
    CitationAudit,
    EvidenceScore,
    EvidenceSource,
    ReflectionDecision,
)
from app.schemas.progress import ResearchProgressRecord
from app.services.cache import CacheUnavailableError
from app.services.llm.factory import CanonicalLLMProvider
from app.services.research.execution import (
    ResearchExecutionService,
)
from app.workflow.state import ResearchState


class RecordingResearchRunStore:
    def __init__(self) -> None:
        self.research_run_id = uuid4()
        self.events: list[str] = []
        self.query: str | None = None
        self.llm_provider: CanonicalLLMProvider | None = None
        self.error_message: str | None = None
        self.completed_result: ResearchState | None = None

    async def create_queued(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: CanonicalLLMProvider,
        requested_by_user_id: UUID | None,
        research_run_id: UUID | None = None,
    ) -> UUID:
        self.events.append("queued")
        self.query = query
        self.llm_provider = llm_provider

        if research_run_id is not None:
            self.research_run_id = research_run_id

        return self.research_run_id

    async def mark_running(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> None:
        assert research_run_id == self.research_run_id
        self.events.append("running")

    async def mark_completed(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        result: ResearchState | None = None,
    ) -> None:
        assert research_run_id == self.research_run_id
        self.events.append("completed")
        self.completed_result = result

    async def mark_failed(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        error_message: str,
    ) -> None:
        assert research_run_id == self.research_run_id
        self.events.append("failed")
        self.error_message = error_message

    async def mark_cancelled(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> bool:
        assert research_run_id == self.research_run_id
        self.events.append("cancelled")
        return True


class RecordingWorkflow:
    def __init__(
        self,
        *,
        result: ResearchState | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.inputs: list[ResearchState] = []
        self.close_calls = 0

    async def ainvoke(
        self,
        state: ResearchState,
    ) -> ResearchState:
        self.inputs.append(state)

        if self.error is not None:
            raise self.error

        assert self.result is not None

        return self.result

    async def close(self) -> None:
        self.close_calls += 1


class RecordingResearchResultCache:
    def __init__(
        self,
        *,
        result: CachedResearchResult | None = None,
        get_error: CacheUnavailableError | None = None,
        set_error: CacheUnavailableError | None = None,
    ) -> None:
        self.result = result
        self.get_error = get_error
        self.set_error = set_error
        self.get_calls: list[
            tuple[
                UUID,
                CanonicalLLMProvider,
                str,
            ]
        ] = []
        self.set_calls: list[
            tuple[
                UUID,
                str,
                CachedResearchResult,
            ]
        ] = []

    async def get(
        self,
        *,
        tenant_id: UUID,
        llm_provider: CanonicalLLMProvider,
        query: str,
    ) -> CachedResearchResult | None:
        self.get_calls.append(
            (
                tenant_id,
                llm_provider,
                query,
            )
        )

        if self.get_error is not None:
            raise self.get_error

        return self.result

    async def set(
        self,
        *,
        tenant_id: UUID,
        query: str,
        result: CachedResearchResult,
    ) -> None:
        self.set_calls.append(
            (
                tenant_id,
                query,
                result,
            )
        )

        if self.set_error is not None:
            raise self.set_error


class RecordingResearchProgressStore:
    def __init__(
        self,
        *,
        error: CacheUnavailableError | None = None,
    ) -> None:
        self.error = error
        self.calls: list[tuple[UUID, ResearchProgressRecord]] = []

    async def set(
        self,
        *,
        tenant_id: UUID,
        record: ResearchProgressRecord,
    ) -> None:
        self.calls.append((tenant_id, record))

        if self.error is not None:
            raise self.error


@pytest.mark.anyio
async def test_execution_publishes_lifecycle_progress() -> None:
    store = RecordingResearchRunStore()
    progress_store = RecordingResearchProgressStore()
    tenant_id = uuid4()
    workflow = RecordingWorkflow(
        result={
            "query": "Explain epoll.",
            "status": "direct_answer_completed",
            "answer": "epoll observes file descriptors.",
        }
    )
    service = ResearchExecutionService(
        store,
        lambda _: workflow,
        progress_store=progress_store,
    )

    await service.execute(
        tenant_id=tenant_id,
        query="Explain epoll.",
        llm_provider="qwen",
    )

    assert [record.status for _, record in progress_store.calls] == [
        "queued",
        "running",
        "completed",
    ]
    assert all(call_tenant == tenant_id for call_tenant, _ in progress_store.calls)
    completed_record = progress_store.calls[-1][1]
    assert completed_record.research_run_id == store.research_run_id
    assert completed_record.workflow_status == "direct_answer_completed"


@pytest.mark.anyio
async def test_execution_can_persist_queue_before_background_work() -> None:
    store = RecordingResearchRunStore()
    progress_store = RecordingResearchProgressStore()
    workflow = RecordingWorkflow(
        result={
            "query": "Explain epoll.",
            "status": "direct_answer_completed",
            "answer": "epoll observes file descriptors.",
        }
    )
    service = ResearchExecutionService(
        store,
        lambda _: workflow,
        progress_store=progress_store,
    )

    queued = await service.queue(
        tenant_id=uuid4(),
        query="  Explain epoll.  ",
        llm_provider="qwen",
    )

    assert store.events == ["queued"]
    assert queued.query == "Explain epoll."
    assert queued.llm_provider == "ollama"
    assert [record.status for _, record in progress_store.calls] == ["queued"]

    result = await service.execute_queued(queued)

    assert result.research_run_id == queued.research_run_id
    assert store.events == ["queued", "running", "completed"]


@pytest.mark.anyio
async def test_execution_publishes_failure_progress() -> None:
    store = RecordingResearchRunStore()
    progress_store = RecordingResearchProgressStore()
    workflow = RecordingWorkflow(error=RuntimeError("Search timed out."))
    service = ResearchExecutionService(
        store,
        lambda _: workflow,
        progress_store=progress_store,
    )

    with pytest.raises(RuntimeError, match="Search timed out"):
        await service.execute(
            tenant_id=uuid4(),
            query="Compare HTTP versions.",
            llm_provider="qwen",
        )

    assert [record.status for _, record in progress_store.calls] == [
        "queued",
        "running",
        "failed",
    ]
    assert progress_store.calls[-1][1].error_message == "Search timed out."


@pytest.mark.anyio
async def test_execution_fails_open_when_progress_store_is_unavailable() -> None:
    store = RecordingResearchRunStore()
    progress_store = RecordingResearchProgressStore(
        error=CacheUnavailableError("Redis is unavailable."),
    )
    workflow = RecordingWorkflow(
        result={
            "query": "Explain epoll.",
            "status": "direct_answer_completed",
        }
    )
    service = ResearchExecutionService(
        store,
        lambda _: workflow,
        progress_store=progress_store,
    )

    result = await service.execute(
        tenant_id=uuid4(),
        query="Explain epoll.",
        llm_provider="qwen",
    )

    assert result.state["status"] == "direct_answer_completed"
    assert store.events == ["queued", "running", "completed"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("provider", "canonical_provider"),
    [
        (
            "qwen",
            "ollama",
        ),
        (
            "claude",
            "anthropic",
        ),
    ],
)
async def test_execution_normalizes_provider_and_completes(
    provider: str,
    canonical_provider: CanonicalLLMProvider,
) -> None:
    store = RecordingResearchRunStore()
    workflow_result: ResearchState = {
        "query": "Explain Linux epoll.",
        "route": "direct",
        "route_reason": "The question uses stable knowledge.",
        "answer": "epoll is a Linux I/O event notification interface.",
        "status": "direct_answer_completed",
    }
    workflow = RecordingWorkflow(
        result=workflow_result,
    )
    provider_calls: list[CanonicalLLMProvider] = []

    def create_workflow(
        selected_provider: CanonicalLLMProvider,
    ) -> RecordingWorkflow:
        provider_calls.append(selected_provider)

        return workflow

    service = ResearchExecutionService(
        store,
        create_workflow,
    )

    tenant_id = uuid4()
    result = await service.execute(
        tenant_id=tenant_id,
        query="  Explain Linux epoll.  ",
        llm_provider=provider,
    )

    assert result.research_run_id == store.research_run_id
    assert result.llm_provider == canonical_provider
    assert result.state == workflow_result

    assert store.query == "Explain Linux epoll."
    assert store.llm_provider == canonical_provider
    assert store.events == [
        "queued",
        "running",
        "completed",
    ]

    assert provider_calls == [
        canonical_provider,
    ]
    assert workflow.inputs == [
        {
            "query": "Explain Linux epoll.",
            "tenant_id": tenant_id,
        }
    ]

    assert workflow.close_calls == 1

    assert result.cache_hit is False


@pytest.mark.anyio
async def test_execution_marks_run_failed_and_reraises() -> None:
    store = RecordingResearchRunStore()
    workflow = RecordingWorkflow(
        error=RuntimeError(
            "Tavily search provider timed out.",
        ),
    )
    service = ResearchExecutionService(
        store,
        lambda _: workflow,
    )

    with pytest.raises(
        RuntimeError,
        match="Tavily search provider timed out",
    ):
        await service.execute(
            tenant_id=uuid4(),
            query="Compare HTTP/2 and HTTP/3.",
            llm_provider="qwen",
        )

    assert store.events == [
        "queued",
        "running",
        "failed",
    ]
    assert store.error_message == ("Tavily search provider timed out.")

    assert workflow.close_calls == 1


@pytest.mark.anyio
async def test_execution_rejects_invalid_provider_before_persistence() -> None:
    store = RecordingResearchRunStore()
    service = ResearchExecutionService(
        store,
    )

    with pytest.raises(
        ValueError,
        match="Unsupported LLM provider",
    ):
        await service.execute(
            tenant_id=uuid4(),
            query="Explain DNS recursive resolution.",
            llm_provider="openai",
        )

    assert store.events == []


@pytest.mark.anyio
async def test_execution_rejects_blank_query_before_persistence() -> None:
    store = RecordingResearchRunStore()
    service = ResearchExecutionService(
        store,
    )

    with pytest.raises(
        ValueError,
        match="query must not be empty",
    ):
        await service.execute(
            tenant_id=uuid4(),
            query="   ",
            llm_provider="qwen",
        )

    assert store.events == []


@pytest.mark.anyio
async def test_execution_uses_cached_result_without_workflow() -> None:
    store = RecordingResearchRunStore()
    tenant_id = uuid4()
    cached_result = CachedResearchResult(
        llm_provider="ollama",
        workflow_status="direct_answer_completed",
        route="direct",
        route_reason=("The question can be answered using stable knowledge."),
        answer="A mutex protects a critical section.",
    )
    cache = RecordingResearchResultCache(
        result=cached_result,
    )
    workflow = RecordingWorkflow(
        result={
            "query": "This workflow should not run.",
        },
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

    result = await service.execute(
        tenant_id=tenant_id,
        query="  What is a mutex?  ",
        llm_provider="qwen",
    )

    assert result.cache_hit is True
    assert result.state == {
        "query": "What is a mutex?",
        "status": "direct_answer_completed",
        "route": "direct",
        "route_reason": ("The question can be answered using stable knowledge."),
        "answer": "A mutex protects a critical section.",
    }
    assert workflow_factory_calls == []
    assert workflow.inputs == []
    assert workflow.close_calls == 0
    assert store.events == [
        "queued",
        "running",
        "completed",
    ]
    assert cache.get_calls == [
        (
            tenant_id,
            "ollama",
            "What is a mutex?",
        )
    ]
    assert cache.set_calls == []


@pytest.mark.anyio
async def test_cache_hit_restores_report_evidence_for_durable_persistence() -> None:
    store = RecordingResearchRunStore()
    source = EvidenceSource(
        source_id="WEB-0123456789ABCDEF",
        origin="web",
        title="HTTP specification",
        locator="https://example.com/http",
        content="HTTP evidence.",
        provider="fixture",
    )
    score = EvidenceScore(
        source_id=source.source_id,
        relevance=0.9,
        content_quality=0.8,
        traceability=1,
        overall=0.88,
    )
    audit = CitationAudit(
        valid=True,
        cited_source_ids=[source.source_id],
        unknown_source_ids=[],
        uncited_claims=[],
        coverage_ratio=1,
    )
    reflection = ReflectionDecision(
        status="approved",
        reasons=[],
        evidence_count=1,
        average_evidence_score=0.88,
    )
    cache = RecordingResearchResultCache(
        result=CachedResearchResult(
            llm_provider="ollama",
            workflow_status="research_report_completed",
            route="deep_research",
            answer=f"HTTP report. [{source.source_id}]",
            report=f"HTTP report. [{source.source_id}]",
            evidence_sources=[source],
            evidence_scores=[score],
            citation_audit=audit,
            reflection=reflection,
            reflection_attempts=2,
        )
    )
    workflow = RecordingWorkflow(result={"query": "must not run"})
    service = ResearchExecutionService(
        store,
        lambda _: workflow,
        result_cache=cache,
    )

    result = await service.execute(
        tenant_id=uuid4(),
        query="Compare HTTP transports.",
        llm_provider="qwen",
    )

    assert result.cache_hit is True
    assert result.state["report"] == f"HTTP report. [{source.source_id}]"
    assert result.state["evidence_sources"] == [source]
    assert result.state["evidence_scores"] == [score]
    assert result.state["reflection_attempts"] == 2
    assert store.completed_result == result.state
    assert workflow.inputs == []


@pytest.mark.anyio
async def test_execution_runs_workflow_after_cache_miss() -> None:
    store = RecordingResearchRunStore()
    tenant_id = uuid4()
    cache = RecordingResearchResultCache(
        result=None,
    )
    workflow_result: ResearchState = {
        "query": "Explain Linux epoll.",
        "status": "direct_answer_completed",
        "route": "direct",
        "answer": "epoll monitors multiple file descriptors.",
    }
    workflow = RecordingWorkflow(
        result=workflow_result,
    )
    service = ResearchExecutionService(
        store,
        lambda _: workflow,
        result_cache=cache,
    )

    result = await service.execute(
        tenant_id=tenant_id,
        query="Explain Linux epoll.",
        llm_provider="qwen",
    )

    assert result.cache_hit is False
    assert result.state == workflow_result
    assert workflow.inputs == [
        {
            "query": "Explain Linux epoll.",
            "tenant_id": tenant_id,
        }
    ]
    assert workflow.close_calls == 1
    assert store.events == [
        "queued",
        "running",
        "completed",
    ]
    assert cache.set_calls == [
        (
            tenant_id,
            "Explain Linux epoll.",
            CachedResearchResult(
                llm_provider="ollama",
                workflow_status="direct_answer_completed",
                route="direct",
                answer="epoll monitors multiple file descriptors.",
            ),
        )
    ]


@pytest.mark.anyio
async def test_execution_fails_open_when_cache_read_is_unavailable() -> None:
    store = RecordingResearchRunStore()
    cache = RecordingResearchResultCache(
        get_error=CacheUnavailableError("Redis is unavailable."),
    )
    workflow_result: ResearchState = {
        "query": "Explain DNS recursive resolution.",
        "status": "direct_answer_completed",
        "route": "direct",
        "answer": "A recursive resolver queries DNS servers.",
    }
    workflow = RecordingWorkflow(
        result=workflow_result,
    )
    service = ResearchExecutionService(
        store,
        lambda _: workflow,
        result_cache=cache,
    )

    result = await service.execute(
        tenant_id=uuid4(),
        query="Explain DNS recursive resolution.",
        llm_provider="qwen",
    )

    assert result.cache_hit is False
    assert result.state == workflow_result
    assert workflow.close_calls == 1
    assert store.events == [
        "queued",
        "running",
        "completed",
    ]


@pytest.mark.anyio
async def test_execution_fails_open_when_cache_write_is_unavailable() -> None:
    store = RecordingResearchRunStore()
    cache = RecordingResearchResultCache(
        result=None,
        set_error=CacheUnavailableError(
            "Redis is unavailable.",
        ),
    )
    workflow_result: ResearchState = {
        "query": "Explain HTTP keep-alive.",
        "status": "direct_answer_completed",
        "route": "direct",
        "answer": "Keep-alive allows multiple requests over one connection.",
    }
    workflow = RecordingWorkflow(
        result=workflow_result,
    )
    service = ResearchExecutionService(
        store,
        lambda _: workflow,
        result_cache=cache,
    )
    tenant_id = uuid4()

    result = await service.execute(
        tenant_id=tenant_id,
        query="Explain HTTP keep-alive.",
        llm_provider="qwen",
    )

    assert result.cache_hit is False
    assert result.state == workflow_result
    assert store.events == [
        "queued",
        "running",
        "completed",
    ]
    assert cache.set_calls == [
        (
            tenant_id,
            "Explain HTTP keep-alive.",
            CachedResearchResult(
                llm_provider="ollama",
                workflow_status="direct_answer_completed",
                route="direct",
                answer=("Keep-alive allows multiple requests over one connection."),
            ),
        )
    ]


@pytest.mark.anyio
async def test_execution_cancels_durable_run_and_publishes_progress() -> None:
    store = RecordingResearchRunStore()
    progress_store = RecordingResearchProgressStore()
    service = ResearchExecutionService(store, progress_store=progress_store)
    tenant_id = uuid4()

    cancelled = await service.cancel(
        tenant_id=tenant_id,
        research_run_id=store.research_run_id,
    )

    assert cancelled is True
    assert store.events == ["cancelled"]
    assert [record.status for _, record in progress_store.calls] == ["cancelled"]
