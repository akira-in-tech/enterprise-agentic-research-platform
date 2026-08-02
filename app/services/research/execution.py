import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, cast
from uuid import UUID

from app.agents.local_scout import LocalScoutAgent
from app.schemas.cache import CachedResearchResult
from app.schemas.progress import ResearchProgressRecord, ResearchProgressStatus
from app.services.cache import CacheUnavailableError
from app.services.llm.base import ClosableLLMClient
from app.services.llm.factory import (
    CanonicalLLMProvider,
    create_llm_client,
    normalize_llm_provider,
)
from app.workflow.graph import (
    ResearchGraph,
    build_research_graph_for_client,
)
from app.workflow.state import ResearchState

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
    ) -> None:
        self._graph = graph
        self._close_callback = close_callback

    async def ainvoke(
        self,
        state: ResearchState,
    ) -> ResearchState:
        result = await self._graph.ainvoke(
            state,
        )

        return cast(
            ResearchState,
            result,
        )

    async def close(self) -> None:
        """Release workflow-owned resources."""

        await self._close_callback()


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


class ResearchResultCache(Protocol):
    """Represent optional research-result cache operations."""

    async def get(
        self,
        *,
        tenant_id: UUID,
        llm_provider: CanonicalLLMProvider,
        query: str,
    ) -> CachedResearchResult | None:
        """Return one cached result or a cache miss."""

    async def set(
        self,
        *,
        tenant_id: UUID,
        query: str,
        result: CachedResearchResult,
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


WorkflowFactory = Callable[
    [CanonicalLLMProvider],
    ResearchWorkflow,
]


def create_default_workflow(
    provider: CanonicalLLMProvider,
    *,
    local_scout: LocalScoutAgent | None = None,
) -> ResearchWorkflow:
    """Build one managed production workflow."""

    llm_client: ClosableLLMClient = create_llm_client(
        provider,
    )

    return LangGraphResearchWorkflow(
        build_research_graph_for_client(
            llm_client,
            local_scout=local_scout,
        ),
        llm_client.close,
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


class ResearchExecutionService:
    """Coordinate persistence and one research workflow execution."""

    def __init__(
        self,
        store: ResearchRunStore,
        workflow_factory: WorkflowFactory = create_default_workflow,
        *,
        result_cache: ResearchResultCache | None = None,
        progress_store: ResearchProgressPublisher | None = None,
    ) -> None:
        self._store = store
        self._workflow_factory = workflow_factory
        self._result_cache = result_cache
        self._progress_store = progress_store

    async def execute(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: str,
        requested_by_user_id: UUID | None = None,
        research_run_id: UUID | None = None,
    ) -> ResearchExecutionResult:
        """Execute one durable research request."""

        queued = await self.queue(
            tenant_id=tenant_id,
            query=query,
            llm_provider=llm_provider,
            requested_by_user_id=requested_by_user_id,
            research_run_id=research_run_id,
        )

        return await self.execute_queued(queued)

    async def queue(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: str,
        requested_by_user_id: UUID | None = None,
        research_run_id: UUID | None = None,
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

        try:
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
                initial_state: ResearchState = {
                    "query": normalized_query,
                    "tenant_id": tenant_id,
                }

                try:
                    final_state = await workflow.ainvoke(
                        initial_state,
                    )
                finally:
                    await workflow.close()

                cache_hit = False

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
            error_message = "Research execution was cancelled during application shutdown."
            await self._store.mark_failed(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
                error_message=error_message,
            )
            await self._publish_progress(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
                status="failed",
                message="Research workflow was cancelled.",
                error_message=error_message,
            )
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
            )

        return ResearchExecutionResult(
            research_run_id=research_run_id,
            llm_provider=canonical_provider,
            state=final_state,
            cache_hit=cache_hit,
        )

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
    ) -> CachedResearchResult | None:
        """Read the optional cache without breaking research execution."""

        if self._result_cache is None:
            return None

        try:
            return await self._result_cache.get(
                tenant_id=tenant_id,
                llm_provider=llm_provider,
                query=query,
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
