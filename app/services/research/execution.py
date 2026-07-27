from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, cast
from uuid import UUID

from app.services.llm.factory import (
    CanonicalLLMProvider,
    normalize_llm_provider,
)
from app.workflow.graph import (
    ResearchGraph,
    build_default_research_graph,
)
from app.workflow.state import ResearchState


class ResearchWorkflow(Protocol):
    """Represent the workflow interface required by the service."""

    async def ainvoke(
        self,
        state: ResearchState,
    ) -> ResearchState:
        """Execute one research workflow."""


class LangGraphResearchWorkflow:
    """Adapt LangGraph's overloaded API to the application interface."""

    def __init__(
        self,
        graph: ResearchGraph,
    ) -> None:
        self._graph = graph

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


WorkflowFactory = Callable[
    [CanonicalLLMProvider],
    ResearchWorkflow,
]


def create_default_workflow(
    provider: CanonicalLLMProvider,
) -> ResearchWorkflow:
    """Build the production workflow for one canonical provider."""

    return LangGraphResearchWorkflow(
        build_default_research_graph(provider),
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


class ResearchExecutionService:
    """Coordinate persistence and one research workflow execution."""

    def __init__(
        self,
        store: ResearchRunStore,
        workflow_factory: WorkflowFactory = create_default_workflow,
    ) -> None:
        self._store = store
        self._workflow_factory = workflow_factory

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

            workflow = self._workflow_factory(
                canonical_provider,
            )
            initial_state: ResearchState = {
                "query": normalized_query,
            }
            final_state = await workflow.ainvoke(
                initial_state,
            )

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
        )

    @staticmethod
    def _format_error(
        error: Exception,
    ) -> str:
        message = str(error).strip()

        if not message:
            message = type(error).__name__

        return message[:4_000]
