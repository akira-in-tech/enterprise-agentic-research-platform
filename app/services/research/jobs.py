import asyncio
import logging
from typing import Protocol
from uuid import UUID

from app.services.research.execution import (
    QueuedResearchExecution,
    ResearchExecutionResult,
)

logger = logging.getLogger(__name__)


class BackgroundResearchExecutor(Protocol):
    """Queue durable runs and execute them after the API accepts the job."""

    async def queue(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: str,
        requested_by_user_id: UUID | None = None,
        research_run_id: UUID | None = None,
    ) -> QueuedResearchExecution:
        """Persist one queued run."""

    async def execute_queued(
        self,
        queued: QueuedResearchExecution,
    ) -> ResearchExecutionResult:
        """Execute a previously persisted run."""


class ResearchJobManager:
    """Own in-process tasks for durably identified research jobs."""

    def __init__(self, executor: BackgroundResearchExecutor) -> None:
        self._executor = executor
        self._tasks: set[asyncio.Task[ResearchExecutionResult]] = set()
        self._closed = False

    async def submit(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: str,
        requested_by_user_id: UUID | None = None,
    ) -> UUID:
        """Persist one queued run and start its background execution."""

        if self._closed:
            raise RuntimeError("Research job manager is closed.")

        queued = await self._executor.queue(
            tenant_id=tenant_id,
            query=query,
            llm_provider=llm_provider,
            requested_by_user_id=requested_by_user_id,
        )
        task = asyncio.create_task(
            self._executor.execute_queued(queued),
            name=f"research-run-{queued.research_run_id}",
        )
        self._tasks.add(task)
        task.add_done_callback(self._task_completed)

        return queued.research_run_id

    async def close(self) -> None:
        """Cancel and await outstanding tasks during application shutdown."""

        self._closed = True
        tasks = tuple(self._tasks)

        for task in tasks:
            task.cancel()

        if tasks:
            await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

        self._tasks.clear()

    def _task_completed(
        self,
        task: asyncio.Task[ResearchExecutionResult],
    ) -> None:
        self._tasks.discard(task)

        if task.cancelled():
            return

        error = task.exception()

        if error is not None:
            logger.error(
                "Background research execution failed.",
                exc_info=(type(error), error, error.__traceback__),
            )
