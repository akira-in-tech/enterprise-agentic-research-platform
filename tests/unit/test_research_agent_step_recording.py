from uuid import UUID, uuid4

import pytest

from app.agents.reflection import ReflectionAgent
from app.schemas.evidence import CitationAudit, EvidenceScore, EvidenceSource, ReflectionDecision
from app.schemas.intent import IntentDecision
from app.schemas.planner import ReportSection, ResearchPlan, ResearchTask
from app.schemas.progress import ResearchProgressRecord
from app.services.evidence import CitationValidator
from app.services.research.execution import LangGraphResearchWorkflow, ResearchExecutionService
from app.workflow.graph import build_eight_agent_research_graph
from app.workflow.state import ResearchState


async def unexpected(*_: object, **__: object) -> object:
    raise AssertionError("Deep-research agents must not run for the direct route.")


async def classify_direct(_: str) -> IntentDecision:
    return IntentDecision(route="direct", reason="Stable knowledge is sufficient.")


async def create_plan(_: str) -> ResearchPlan:
    return ResearchPlan(
        goal="Unused for the direct route.",
        sub_questions=["Unused."],
        tasks=[
            ResearchTask(
                title="Unused",
                search_query="unused",
                rationale="Unused.",
            )
        ],
        report_outline=[ReportSection(title="Conclusion", purpose="Unused.")],
    )


async def generate_direct_answer(query: str) -> str:
    return f"Direct: {query}"


def approved_review(
    report: str,
    sources: list[EvidenceSource],
    scores: list[EvidenceScore],
    is_high_risk_domain: bool = False,
) -> tuple[CitationAudit, ReflectionDecision]:
    audit = CitationValidator().validate(report=report, sources=sources)
    decision = ReflectionAgent().review(
        citation_audit=audit,
        evidence_scores=scores,
        is_high_risk_domain=is_high_risk_domain,
    )

    return audit, decision


def build_direct_route_workflow() -> LangGraphResearchWorkflow:
    graph = build_eight_agent_research_graph(
        classify_direct,
        create_plan,
        generate_direct_answer,
        unexpected,  # type: ignore[arg-type]
        unexpected,  # type: ignore[arg-type]
        unexpected,  # type: ignore[arg-type]
        unexpected,  # type: ignore[arg-type]
        unexpected,  # type: ignore[arg-type]
        unexpected,  # type: ignore[arg-type]
        approved_review,
    )

    async def close() -> None:
        return None

    return LangGraphResearchWorkflow(graph, close)


@pytest.mark.anyio
async def test_step_recording_traces_each_agent_in_order() -> None:
    workflow = build_direct_route_workflow()
    recorded: list[tuple[str, str, str | None]] = []

    async def recorder(agent_role: str, status: str, summary: str | None) -> None:
        recorded.append((agent_role, status, summary))

    workflow.configure_step_recording(recorder)

    result = await workflow.ainvoke(
        {
            "query": "Explain idempotency.",
            "tenant_id": uuid4(),
        }
    )

    assert result["route"] == "direct"
    assert result["answer"] == "Direct: Explain idempotency."
    assert recorded == [
        ("intent_router", "started", None),
        ("intent_router", "completed", None),
        ("direct_answer", "started", None),
        ("direct_answer", "completed", None),
    ]


@pytest.mark.anyio
async def test_step_recording_returns_the_same_final_state_as_without_recording() -> None:
    state: ResearchState = {
        "query": "Explain idempotency.",
        "tenant_id": uuid4(),
    }

    recorded_workflow = build_direct_route_workflow()

    async def recorder(*_: object) -> None:
        return None

    recorded_workflow.configure_step_recording(recorder)
    with_recording = await recorded_workflow.ainvoke(state)

    plain_workflow = build_direct_route_workflow()
    without_recording = await plain_workflow.ainvoke(state)

    assert with_recording == without_recording


@pytest.mark.anyio
async def test_step_recording_records_a_failed_step() -> None:
    async def failing_direct_answer(_: str) -> str:
        raise RuntimeError("Provider unavailable.")

    graph = build_eight_agent_research_graph(
        classify_direct,
        create_plan,
        failing_direct_answer,
        unexpected,  # type: ignore[arg-type]
        unexpected,  # type: ignore[arg-type]
        unexpected,  # type: ignore[arg-type]
        unexpected,  # type: ignore[arg-type]
        unexpected,  # type: ignore[arg-type]
        unexpected,  # type: ignore[arg-type]
        approved_review,
    )

    async def close() -> None:
        return None

    workflow = LangGraphResearchWorkflow(graph, close)
    recorded: list[tuple[str, str, str | None]] = []

    async def recorder(agent_role: str, status: str, summary: str | None) -> None:
        recorded.append((agent_role, status, summary))

    workflow.configure_step_recording(recorder)

    with pytest.raises(RuntimeError, match="Provider unavailable."):
        await workflow.ainvoke(
            {
                "query": "Explain idempotency.",
                "tenant_id": uuid4(),
            }
        )

    assert recorded == [
        ("intent_router", "started", None),
        ("intent_router", "completed", None),
        ("direct_answer", "started", None),
        ("direct_answer", "failed", "Provider unavailable."),
    ]


class FailingAgentStepStore:
    """Simulate a durable step store that always fails to append."""

    async def append(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        sequence: int,
        agent_role: str,
        status: str,
        summary: str | None = None,
    ) -> None:
        raise RuntimeError("Postgres is unavailable.")


class RecordingAgentStepStore:
    """Record every appended step without touching a real database."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def append(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        sequence: int,
        agent_role: str,
        status: str,
        summary: str | None = None,
    ) -> None:
        self.calls.append((agent_role, status))


class RecordingResearchProgressStore:
    """Record every published progress snapshot without touching Redis."""

    def __init__(self) -> None:
        self.calls: list[ResearchProgressRecord] = []

    async def set(
        self,
        *,
        tenant_id: UUID,
        record: ResearchProgressRecord,
    ) -> None:
        self.calls.append(record)


class RecordingResearchRunStoreForSteps:
    def __init__(self) -> None:
        self.research_run_id = uuid4()

    async def create_queued(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: str,
        requested_by_user_id: UUID | None,
        research_run_id: UUID | None = None,
    ) -> UUID:
        if research_run_id is not None:
            self.research_run_id = research_run_id
        return self.research_run_id

    async def mark_running(self, *, tenant_id: UUID, research_run_id: UUID) -> None:
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

    async def mark_cancelled(self, *, tenant_id: UUID, research_run_id: UUID) -> bool:
        return True


@pytest.mark.anyio
async def test_execution_service_survives_a_failing_agent_step_store() -> None:
    store = RecordingResearchRunStoreForSteps()
    workflow = build_direct_route_workflow()
    service = ResearchExecutionService(
        store,
        lambda _: workflow,
        agent_step_store=FailingAgentStepStore(),
    )

    result = await service.execute(
        tenant_id=uuid4(),
        query="Explain idempotency.",
        llm_provider="qwen",
    )

    assert result.state["answer"] == "Direct: Explain idempotency."


@pytest.mark.anyio
async def test_step_start_publishes_live_progress_with_the_node_name() -> None:
    store = RecordingResearchRunStoreForSteps()
    progress_store = RecordingResearchProgressStore()
    workflow = build_direct_route_workflow()
    service = ResearchExecutionService(
        store,
        lambda _: workflow,
        agent_step_store=RecordingAgentStepStore(),
        progress_store=progress_store,
    )

    await service.execute(
        tenant_id=uuid4(),
        query="Explain idempotency.",
        llm_provider="qwen",
    )

    workflow_statuses = [record.workflow_status for record in progress_store.calls]
    assert workflow_statuses == [
        None,  # queued
        None,  # running (published before the workflow starts)
        "intent_router",  # intent_router started
        "direct_answer",  # direct_answer started
        "direct_answer_completed",  # completed, from the final state
    ]
    assert all(record.status == "running" for record in progress_store.calls[2:4])
