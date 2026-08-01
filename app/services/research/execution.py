import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol, cast
from uuid import UUID

from app.schemas.cache import CachedResearchResult
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
    """Represent optional research-result cache reads."""

    async def get(
        self,
        *,
        tenant_id: UUID,
        llm_provider: CanonicalLLMProvider,
        query: str,
    ) -> CachedResearchResult | None:
        """Return one cached result or a cache miss."""


WorkflowFactory = Callable[
    [CanonicalLLMProvider],
    ResearchWorkflow,
]


def create_default_workflow(
    provider: CanonicalLLMProvider,
) -> ResearchWorkflow:
    """Build one managed production workflow."""

    llm_client: ClosableLLMClient = create_llm_client(
        provider,
    )

    return LangGraphResearchWorkflow(
        build_research_graph_for_client(
            llm_client,
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


class ResearchExecutionService:
    """Coordinate persistence and one research workflow execution."""

    def __init__(
        self,
        store: ResearchRunStore,
        workflow_factory: WorkflowFactory = create_default_workflow,
        *,
        result_cache: ResearchResultCache | None = None,
    ) -> None:
        self._store = store
        self._workflow_factory = workflow_factory
        self._result_cache = result_cache

    async def execute(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: str,
        requested_by_user_id: UUID | None = None,
    ) -> ResearchExecutionResult:
        """Execute one durable research request."""

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
        )

        try:
            await self._store.mark_running(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
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
            )

        except Exception as error:
            await self._store.mark_failed(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
                error_message=self._format_error(error),
            )
            raise

        return ResearchExecutionResult(
            research_run_id=research_run_id,
            llm_provider=canonical_provider,
            state=final_state,
            cache_hit=cache_hit,
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

        return state

    @staticmethod
    def _format_error(
        error: Exception,
    ) -> str:
        message = str(error).strip()

        if not message:
            message = type(error).__name__

        return message[:4_000]
