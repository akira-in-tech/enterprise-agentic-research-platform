from collections.abc import Sequence
from dataclasses import dataclass

from app.schemas.planner import ResearchTask
from app.schemas.source import WebSource
from app.services.search.executor import ResearchTaskResult, SearchExecutor
from app.services.search.results import build_web_source_pool


@dataclass(frozen=True, slots=True)
class WebScoutResult:
    """Collect canonical web sources and per-task outcomes."""

    outcomes: list[ResearchTaskResult]
    sources: list[WebSource]


class WebScoutAgent:
    """Retrieve and normalize public web sources for research tasks."""

    def __init__(self, executor: SearchExecutor) -> None:
        self._executor = executor

    async def scout(
        self,
        tasks: Sequence[ResearchTask],
    ) -> WebScoutResult:
        """Execute one task batch and build a stable source pool."""

        outcomes = await self._executor.execute_tasks(tasks)
        sources = build_web_source_pool(
            result for outcome in outcomes for result in outcome.results
        )

        return WebScoutResult(
            outcomes=outcomes,
            sources=sources,
        )
