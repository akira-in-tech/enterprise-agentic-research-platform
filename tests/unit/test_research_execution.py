from uuid import UUID, uuid4

import pytest

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

    async def create_queued(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: CanonicalLLMProvider,
        requested_by_user_id: UUID | None,
    ) -> UUID:
        self.events.append("queued")
        self.query = query
        self.llm_provider = llm_provider

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
    ) -> None:
        assert research_run_id == self.research_run_id
        self.events.append("completed")

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

    result = await service.execute(
        tenant_id=uuid4(),
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
        }
    ]

    assert workflow.close_calls == 1


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
