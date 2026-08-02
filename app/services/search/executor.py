import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from app.schemas.planner import ResearchPlan, ResearchTask
from app.services.search.base import SearchClient, SearchResult

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ResearchTaskResult:
    """Store the search outcome for one research task."""

    task: ResearchTask
    results: list[SearchResult]
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        """Return whether the task completed without an error."""

        return self.error is None


class SearchExecutor:
    """Execute the search queries contained in a research plan."""

    def __init__(
        self,
        search_client: SearchClient,
        *,
        max_concurrency: int = 3,
        max_results_per_task: int = 5,
        task_timeout_seconds: float = 15.0,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1.")

        if not 1 <= max_results_per_task <= 20:
            raise ValueError("max_results_per_task must be between 1 and 20.")

        if task_timeout_seconds <= 0:
            raise ValueError("task_timeout_seconds must be greater than 0.")

        self._search_client = search_client
        self._max_concurrency = max_concurrency
        self._max_results_per_task = max_results_per_task
        self._task_timeout_seconds = task_timeout_seconds

    async def execute(
        self,
        plan: ResearchPlan,
    ) -> list[ResearchTaskResult]:
        """Execute all research tasks with bounded concurrency."""

        return await self.execute_tasks(plan.tasks)

    async def execute_tasks(
        self,
        tasks: Sequence[ResearchTask],
    ) -> list[ResearchTaskResult]:
        """Execute an explicit task batch with bounded concurrency."""

        semaphore = asyncio.Semaphore(self._max_concurrency)

        task_coroutines = [self._execute_task(task, semaphore) for task in tasks]

        outcomes = await asyncio.gather(*task_coroutines)

        return list(outcomes)

    async def _execute_task(
        self,
        task: ResearchTask,
        semaphore: asyncio.Semaphore,
    ) -> ResearchTaskResult:
        """Execute one task and isolate provider failures."""

        async with semaphore:
            logger.info(
                "Executing search task | title=%s | query=%s",
                task.title,
                task.search_query,
            )

            try:
                async with asyncio.timeout(self._task_timeout_seconds):
                    results = await self._search_client.search(
                        task.search_query,
                        max_results=self._max_results_per_task,
                    )
            except TimeoutError:
                logger.warning(
                    "Search task timed out | title=%s | timeout_seconds=%s",
                    task.title,
                    self._task_timeout_seconds,
                )

                return ResearchTaskResult(
                    task=task,
                    results=[],
                    error=(
                        f"TimeoutError: search exceeded {self._task_timeout_seconds:g} seconds."
                    ),
                )
            except Exception as error:
                logger.exception(
                    "Search task failed | title=%s",
                    task.title,
                )

                return ResearchTaskResult(
                    task=task,
                    results=[],
                    error=(f"{type(error).__name__}: {error}"),
                )

            logger.info(
                "Search task completed | title=%s | result_count=%s",
                task.title,
                len(results),
            )

            return ResearchTaskResult(
                task=task,
                results=results,
            )
