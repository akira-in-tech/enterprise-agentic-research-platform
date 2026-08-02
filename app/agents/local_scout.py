import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.schemas.planner import ResearchPlan, ResearchTask
from app.schemas.source import PrivateSource

logger = logging.getLogger(__name__)


class PrivateSourceRetriever(Protocol):
    """Describe the private retrieval operation required by Local Scout."""

    async def retrieve(
        self,
        *,
        query: str,
        tenant_id: str,
        limit: int = 5,
    ) -> list[PrivateSource]: ...


@dataclass(frozen=True, slots=True)
class LocalScoutResult:
    """Collect private sources and isolated per-query failures."""

    sources: list[PrivateSource]
    errors: list[str]


class LocalScoutAgent:
    """Retrieve tenant-scoped private evidence for a research plan."""

    def __init__(
        self,
        retriever: PrivateSourceRetriever,
        *,
        max_concurrency: int = 3,
        max_results_per_task: int = 3,
        max_sources: int = 12,
        task_timeout_seconds: float = 15.0,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1.")

        if not 1 <= max_results_per_task <= 20:
            raise ValueError("max_results_per_task must be between 1 and 20.")

        if max_sources < 1:
            raise ValueError("max_sources must be at least 1.")

        if task_timeout_seconds <= 0:
            raise ValueError("task_timeout_seconds must be greater than 0.")

        self._retriever = retriever
        self._max_concurrency = max_concurrency
        self._max_results_per_task = max_results_per_task
        self._max_sources = max_sources
        self._task_timeout_seconds = task_timeout_seconds

    async def scout(
        self,
        plan: ResearchPlan,
        tenant_id: UUID,
    ) -> LocalScoutResult:
        """Run the tasks in a research plan."""

        return await self.scout_tasks(
            plan.tasks,
            tenant_id,
        )

    async def scout_tasks(
        self,
        tasks: Sequence[ResearchTask],
        tenant_id: UUID,
    ) -> LocalScoutResult:
        """Run an explicit task batch and preserve partial successes."""

        semaphore = asyncio.Semaphore(self._max_concurrency)
        outcomes = await asyncio.gather(
            *(
                self._retrieve_task(
                    task,
                    tenant_id=tenant_id,
                    semaphore=semaphore,
                )
                for task in tasks
            )
        )

        sources_by_id: dict[str, PrivateSource] = {}
        source_order: list[str] = []
        errors: list[str] = []

        for sources, error in outcomes:
            if error is not None:
                errors.append(error)

            for source in sources:
                existing = sources_by_id.get(source.source_id)

                if existing is None:
                    source_order.append(source.source_id)
                    sources_by_id[source.source_id] = source
                elif source.score > existing.score:
                    sources_by_id[source.source_id] = source

        deduplicated_sources = [sources_by_id[source_id] for source_id in source_order]

        return LocalScoutResult(
            sources=deduplicated_sources[: self._max_sources],
            errors=errors,
        )

    async def _retrieve_task(
        self,
        task: ResearchTask,
        *,
        tenant_id: UUID,
        semaphore: asyncio.Semaphore,
    ) -> tuple[list[PrivateSource], str | None]:
        """Retrieve one task while isolating timeout and provider failures."""

        async with semaphore:
            try:
                async with asyncio.timeout(self._task_timeout_seconds):
                    sources = await self._retriever.retrieve(
                        query=task.search_query,
                        tenant_id=str(tenant_id),
                        limit=self._max_results_per_task,
                    )
            except TimeoutError:
                message = (
                    f"{task.title}: TimeoutError: private retrieval exceeded "
                    f"{self._task_timeout_seconds:g} seconds."
                )
                logger.warning(message)

                return [], message
            except Exception as error:
                message = f"{task.title}: {type(error).__name__}: {error}"
                logger.exception("Local Scout task failed | title=%s", task.title)

                return [], message

            return sources, None
