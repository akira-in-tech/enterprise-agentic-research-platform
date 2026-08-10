import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import count
from typing import Protocol, cast
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.agents.local_scout import LocalScoutAgent
from app.schemas.cache import CachedResearchResult
from app.schemas.llm import LLMUsage
from app.schemas.progress import ResearchProgressRecord, ResearchProgressStatus
from app.services.cache import CacheUnavailableError
from app.services.llm.base import ClosableLLMClient
from app.services.llm.factory import (
    CanonicalLLMProvider,
    create_llm_client,
    normalize_llm_provider,
)
from app.services.mcp import MCPReferenceScout
from app.workflow.graph import (
    AGENT_STEP_NODE_NAMES,
    ResearchGraph,
    build_research_graph_for_client,
)
from app.workflow.state import ResearchState

AgentStepRecorder = Callable[
    [str, str, str | None],
    Awaitable[None],
]

logger = logging.getLogger(__name__)


class ResearchWorkflow(Protocol):
    """Represent the workflow interface required by the service."""

    async def ainvoke(
        self,
        state: ResearchState,
    ) -> ResearchState:
        """Execute one research workflow."""

    async def close(self) -> None:
        """Release resources owned by this workflow."""


class LangGraphResearchWorkflow:
    """Adapt LangGraph and own its provider client lifecycle."""

    def __init__(
        self,
        graph: ResearchGraph,
        close_callback: Callable[
            [],
            Awaitable[None],
        ],
        usage_callback: Callable[[], LLMUsage] | None = None,
    ) -> None:
        self._graph = graph
        self._close_callback = close_callback
        self._usage_callback = usage_callback
        self._thread_id: str | None = None
        self._resume = False
        self._step_recorder: AgentStepRecorder | None = None

    def configure_durable_execution(
        self,
        *,
        thread_id: str,
        resume: bool,
    ) -> None:
        """Select the durable LangGraph thread and invocation mode."""

        self._thread_id = thread_id
        self._resume = resume

    def configure_step_recording(
        self,
        recorder: AgentStepRecorder | None,
    ) -> None:
        """Record a durable trace row for each canonical agent step."""

        self._step_recorder = recorder

    async def ainvoke(
        self,
        state: ResearchState,
    ) -> ResearchState:
        if self._step_recorder is not None:
            return await self._ainvoke_with_step_recording(state)

        if self._thread_id is None:
            result = await self._graph.ainvoke(state)
        else:
            graph_input = None if self._resume else state
            result = await self._graph.ainvoke(
                graph_input,
                config={"configurable": {"thread_id": self._thread_id}},
            )

        return cast(
            ResearchState,
            result,
        )

    async def _ainvoke_with_step_recording(
        self,
        state: ResearchState,
    ) -> ResearchState:
        """Stream the run so each canonical agent step gets a trace row."""

        recorder = self._step_recorder
        assert recorder is not None

        config: RunnableConfig | None

        if self._thread_id is None:
            graph_input: ResearchState | None = state
            config = None
        else:
            graph_input = None if self._resume else state
            config = {"configurable": {"thread_id": self._thread_id}}

        last_values: ResearchState = state
        # LangGraph only yields a "tasks" finish event for a failed node when
        # another task in the same superstep is still in flight; a lone
        # failing node's exception propagates with no finish event at all.
        # Tracking still-in-flight steps lets the except-block below record
        # those as failed either way.
        in_flight: set[str] = set()

        try:
            async for mode, chunk in self._graph.astream(
                graph_input,
                config=config,
                stream_mode=["tasks", "values"],
            ):
                if mode == "values":
                    last_values = cast(ResearchState, chunk)
                else:
                    await self._record_task_event(
                        cast(dict[str, object], chunk),
                        in_flight,
                    )
        except Exception as error:
            for name in in_flight:
                await recorder(name, "failed", str(error)[:1000])
            raise

        return last_values

    async def _record_task_event(
        self,
        event: dict[str, object],
        in_flight: set[str],
    ) -> None:
        assert self._step_recorder is not None

        name = event.get("name")

        if not isinstance(name, str) or name not in AGENT_STEP_NODE_NAMES:
            return

        if "result" not in event:
            in_flight.add(name)
            await self._step_recorder(name, "started", None)
            return

        in_flight.discard(name)
        error = event.get("error")

        if error is None:
            await self._step_recorder(name, "completed", None)
        else:
            await self._step_recorder(name, "failed", str(error)[:1000])

    async def close(self) -> None:
        """Release workflow-owned resources."""

        await self._close_callback()

    @property
    def usage(self) -> LLMUsage:
        """Return usage accumulated by the workflow's provider client."""

        if self._usage_callback is None:
            return LLMUsage()

        return self._usage_callback()


class ResearchRunStore(Protocol):
    """Represent durable research-run lifecycle operations."""

    async def create_queued(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: CanonicalLLMProvider,
        requested_by_user_id: UUID | None,
        research_run_id: UUID | None = None,
    ) -> UUID:
        """Create and commit one queued research run."""

    async def mark_running(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> None:
        """Commit the transition from queued to running."""

    async def mark_completed(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        result: ResearchState | None = None,
    ) -> None:
        """Commit the transition from running to completed."""

    async def mark_failed(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        error_message: str,
    ) -> None:
        """Commit the transition from an active state to failed."""

    async def mark_cancelled(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> bool:
        """Commit the transition from an active state to cancelled."""


class ResearchResultCache(Protocol):
    """Represent optional research-result cache operations."""

    async def get(
        self,
        *,
        tenant_id: UUID,
        llm_provider: CanonicalLLMProvider,
        query: str,
        document_ids: Sequence[str] | None = None,
    ) -> CachedResearchResult | None:
        """Return one cached result or a cache miss."""

    async def set(
        self,
        *,
        tenant_id: UUID,
        query: str,
        result: CachedResearchResult,
        document_ids: Sequence[str] | None = None,
    ) -> None:
        """Store one completed research result."""


class ResearchProgressPublisher(Protocol):
    """Represent optional research progress publishing."""

    async def set(
        self,
        *,
        tenant_id: UUID,
        record: ResearchProgressRecord,
    ) -> None:
        """Publish the latest lifecycle snapshot."""


class ResearchAgentStepStore(Protocol):
    """Represent optional durable per-agent-step trace recording."""

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
        """Append one step without overwriting prior history."""


WorkflowFactory = Callable[
    [CanonicalLLMProvider],
    ResearchWorkflow,
]


def create_default_workflow(
    provider: CanonicalLLMProvider,
    *,
    local_scout: LocalScoutAgent | None = None,
    mcp_scout: MCPReferenceScout | None = None,
    checkpointer: BaseCheckpointSaver[str] | None = None,
) -> ResearchWorkflow:
    """Build one managed production workflow."""

    llm_client: ClosableLLMClient = create_llm_client(
        provider,
    )

    return LangGraphResearchWorkflow(
        build_research_graph_for_client(
            llm_client,
            local_scout=local_scout,
            mcp_scout=mcp_scout,
            checkpointer=checkpointer,
        ),
        llm_client.close,
        lambda: llm_client.usage,
    )


@dataclass(
    frozen=True,
    slots=True,
)
class ResearchExecutionResult:
    """Return the durable run identity and final workflow state."""

    research_run_id: UUID
    llm_provider: CanonicalLLMProvider
    state: ResearchState
    cache_hit: bool = False
    idempotency_replayed: bool = False
    llm_usage: LLMUsage = field(default_factory=LLMUsage)


@dataclass(
    frozen=True,
    slots=True,
)
class QueuedResearchExecution:
    """Carry one durably queued request into background execution."""

    research_run_id: UUID
    tenant_id: UUID
    requested_by_user_id: UUID | None
    query: str
    llm_provider: CanonicalLLMProvider
    document_ids: list[str] | None = None
    resume: bool = False


class ResearchExecutionService:
    """Coordinate persistence and one research workflow execution."""

    def __init__(
        self,
        store: ResearchRunStore,
        workflow_factory: WorkflowFactory = create_default_workflow,
        *,
        result_cache: ResearchResultCache | None = None,
        progress_store: ResearchProgressPublisher | None = None,
        agent_step_store: ResearchAgentStepStore | None = None,
    ) -> None:
        self._store = store
        self._workflow_factory = workflow_factory
        self._result_cache = result_cache
        self._agent_step_store = agent_step_store
        self._progress_store = progress_store

    async def execute(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: str,
        requested_by_user_id: UUID | None = None,
        research_run_id: UUID | None = None,
        document_ids: Sequence[str] | None = None,
    ) -> ResearchExecutionResult:
        """Execute one durable research request."""

        queued = await self.queue(
            tenant_id=tenant_id,
            query=query,
            llm_provider=llm_provider,
            requested_by_user_id=requested_by_user_id,
            research_run_id=research_run_id,
            document_ids=document_ids,
        )

        return await self.execute_queued(queued)

    async def cancel(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> bool:
        """Durably cancel one queued or running research run."""

        cancelled = await self._store.mark_cancelled(
            tenant_id=tenant_id,
            research_run_id=research_run_id,
        )
        if not cancelled:
            return False
        await self._publish_progress(
            tenant_id=tenant_id,
            research_run_id=research_run_id,
            status="cancelled",
            message="Research workflow was cancelled.",
        )
        return True

    async def queue(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: str,
        requested_by_user_id: UUID | None = None,
        research_run_id: UUID | None = None,
        document_ids: Sequence[str] | None = None,
    ) -> QueuedResearchExecution:
        """Create one durable queued run before asynchronous delivery."""

        normalized_query = query.strip()

        if not normalized_query:
            raise ValueError("query must not be empty.")

        canonical_provider = normalize_llm_provider(
            llm_provider,
        )

        research_run_id = await self._store.create_queued(
            tenant_id=tenant_id,
            requested_by_user_id=requested_by_user_id,
            query=normalized_query,
            llm_provider=canonical_provider,
            research_run_id=research_run_id,
        )
        await self._publish_progress(
            tenant_id=tenant_id,
            research_run_id=research_run_id,
            status="queued",
            message="Research request queued.",
        )

        return QueuedResearchExecution(
            research_run_id=research_run_id,
            tenant_id=tenant_id,
            requested_by_user_id=requested_by_user_id,
            query=normalized_query,
            llm_provider=canonical_provider,
            document_ids=list(document_ids) if document_ids is not None else None,
        )

    async def execute_queued(
        self,
        queued: QueuedResearchExecution,
    ) -> ResearchExecutionResult:
        """Execute a previously persisted queued run."""

        tenant_id = queued.tenant_id
        research_run_id = queued.research_run_id
        normalized_query = queued.query
        canonical_provider = queued.llm_provider
        document_ids = queued.document_ids

        try:
            if not queued.resume:
                await self._store.mark_running(
                    tenant_id=tenant_id,
                    research_run_id=research_run_id,
                )
            await self._publish_progress(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
                status="running",
                message="Research workflow is running.",
            )

            cached_result = await self._get_cached_result(
                tenant_id=tenant_id,
                llm_provider=canonical_provider,
                query=normalized_query,
                document_ids=document_ids,
            )

            if cached_result is not None:
                final_state = self._restore_cached_state(
                    query=normalized_query,
                    result=cached_result,
                )
                cache_hit = True

            else:
                workflow = self._workflow_factory(
                    canonical_provider,
                )
                if isinstance(workflow, LangGraphResearchWorkflow):
                    workflow.configure_durable_execution(
                        thread_id=f"{tenant_id}:{research_run_id}",
                        resume=queued.resume,
                    )
                    if self._agent_step_store is not None:
                        workflow.configure_step_recording(
                            self._build_step_recorder(
                                tenant_id=tenant_id,
                                research_run_id=research_run_id,
                            )
                        )
                initial_state: ResearchState = {
                    "query": normalized_query,
                    "tenant_id": tenant_id,
                }

                if document_ids is not None:
                    initial_state["document_ids"] = document_ids

                try:
                    final_state = await workflow.ainvoke(
                        initial_state,
                    )
                finally:
                    await workflow.close()

                cache_hit = False
                llm_usage = (
                    workflow.usage
                    if isinstance(workflow, LangGraphResearchWorkflow)
                    else LLMUsage()
                )

            if cached_result is not None:
                llm_usage = LLMUsage()

            await self._store.mark_completed(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
                result=final_state,
            )
            await self._publish_progress(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
                status="completed",
                message="Research workflow completed.",
                workflow_status=final_state.get("status"),
            )

        except asyncio.CancelledError:
            # User cancellation is persisted before the task is interrupted.
            # Shutdown and lease-loss interruption deliberately leave an active
            # row recoverable by another worker.
            raise
        except Exception as error:
            error_message = self._format_error(error)
            await self._store.mark_failed(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
                error_message=error_message,
            )
            await self._publish_progress(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
                status="failed",
                message="Research workflow failed.",
                error_message=error_message,
            )
            raise

        if not cache_hit:
            await self._set_cached_result(
                tenant_id=tenant_id,
                llm_provider=canonical_provider,
                query=normalized_query,
                state=final_state,
                document_ids=document_ids,
            )

        return ResearchExecutionResult(
            research_run_id=research_run_id,
            llm_provider=canonical_provider,
            state=final_state,
            cache_hit=cache_hit,
            llm_usage=llm_usage,
        )

    def _build_step_recorder(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> AgentStepRecorder:
        """Build a per-run recorder that assigns a monotonic sequence."""

        agent_step_store = self._agent_step_store
        assert agent_step_store is not None
        sequence = count(1)

        async def record(
            agent_role: str,
            status: str,
            summary: str | None,
        ) -> None:
            try:
                await agent_step_store.append(
                    tenant_id=tenant_id,
                    research_run_id=research_run_id,
                    sequence=next(sequence),
                    agent_role=agent_role,
                    status=status,
                    summary=summary,
                )
            except Exception:
                logger.warning(
                    "Failed to record agent step for tenant %s run %s (role=%s, status=%s).",
                    tenant_id,
                    research_run_id,
                    agent_role,
                    status,
                    exc_info=True,
                )

            if status != "started":
                return

            try:
                await self._publish_progress(
                    tenant_id=tenant_id,
                    research_run_id=research_run_id,
                    status="running",
                    message=f"Running {agent_role.replace('_', ' ')}.",
                    workflow_status=agent_role,
                )
            except Exception:
                logger.warning(
                    "Failed to publish live progress for tenant %s run %s (role=%s).",
                    tenant_id,
                    research_run_id,
                    agent_role,
                    exc_info=True,
                )

        return record

    async def _publish_progress(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        status: ResearchProgressStatus,
        message: str,
        workflow_status: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Publish optional progress without breaking durable execution."""

        if self._progress_store is None:
            return

        record = ResearchProgressRecord(
            research_run_id=research_run_id,
            status=status,
            message=message,
            updated_at=datetime.now(UTC),
            workflow_status=workflow_status,
            error_message=error_message,
        )

        try:
            await self._progress_store.set(
                tenant_id=tenant_id,
                record=record,
            )
        except CacheUnavailableError:
            logger.warning(
                "Research progress publish failed for tenant %s and run %s.",
                tenant_id,
                research_run_id,
                exc_info=True,
            )

    async def _get_cached_result(
        self,
        *,
        tenant_id: UUID,
        llm_provider: CanonicalLLMProvider,
        query: str,
        document_ids: Sequence[str] | None = None,
    ) -> CachedResearchResult | None:
        """Read the optional cache without breaking research execution."""

        if self._result_cache is None:
            return None

        try:
            return await self._result_cache.get(
                tenant_id=tenant_id,
                llm_provider=llm_provider,
                query=query,
                document_ids=document_ids,
            )
        except CacheUnavailableError:
            logger.warning(
                ("Research result cache read failed for tenant %s and provider %s."),
                tenant_id,
                llm_provider,
                exc_info=True,
            )
            return None

    async def _set_cached_result(
        self,
        *,
        tenant_id: UUID,
        llm_provider: CanonicalLLMProvider,
        query: str,
        state: ResearchState,
        document_ids: Sequence[str] | None = None,
    ) -> None:
        """Write a completed result without breaking research execution."""

        if self._result_cache is None:
            return

        workflow_status = state.get("status")

        if not workflow_status:
            return

        result = CachedResearchResult(
            llm_provider=llm_provider,
            workflow_status=workflow_status,
            route=state.get("route"),
            route_reason=state.get("route_reason"),
            answer=state.get("answer"),
            citation_audit=state.get("citation_audit"),
            reflection=state.get("reflection"),
            report=state.get("report"),
            evidence_sources=state.get("evidence_sources", []),
            evidence_scores=state.get("evidence_scores", []),
            reflection_attempts=state.get("reflection_attempts"),
        )

        try:
            await self._result_cache.set(
                tenant_id=tenant_id,
                query=query,
                result=result,
                document_ids=document_ids,
            )
        except CacheUnavailableError:
            logger.warning(
                ("Research result cache write failed for tenant %s and provider %s."),
                tenant_id,
                llm_provider,
                exc_info=True,
            )

    @staticmethod
    def _restore_cached_state(
        *,
        query: str,
        result: CachedResearchResult,
    ) -> ResearchState:
        """Restore API-visible workflow state from a cache payload."""

        state: ResearchState = {
            "query": query,
            "status": result.workflow_status,
        }

        if result.route is not None:
            state["route"] = result.route

        if result.route_reason is not None:
            state["route_reason"] = result.route_reason

        if result.answer is not None:
            state["answer"] = result.answer

        if result.citation_audit is not None:
            state["citation_audit"] = result.citation_audit

        if result.reflection is not None:
            state["reflection"] = result.reflection

        if result.report is not None:
            state["report"] = result.report

        if result.evidence_sources:
            state["evidence_sources"] = result.evidence_sources

        if result.evidence_scores:
            state["evidence_scores"] = result.evidence_scores

        if result.reflection_attempts is not None:
            state["reflection_attempts"] = result.reflection_attempts

        return state

    @staticmethod
    def _format_error(
        error: Exception,
    ) -> str:
        message = str(error).strip()

        if not message:
            message = type(error).__name__

        return message[:4_000]
