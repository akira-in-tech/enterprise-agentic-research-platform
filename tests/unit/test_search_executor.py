import asyncio

import pytest

from app.schemas.planner import ResearchPlan, ResearchTask
from app.services.search.base import SearchResult
from app.services.search.executor import SearchExecutor


class FakeSearchClient:
    """Provide deterministic search behavior for unit tests."""

    def __init__(
        self,
        failing_queries: set[str] | None = None,
        delays: dict[str, float] | None = None,
    ) -> None:
        self.failing_queries = failing_queries or set()
        self.delays = delays or {}
        self.calls: list[tuple[str, int]] = []
        self.active_requests = 0
        self.max_active_requests = 0

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
    ) -> list[SearchResult]:
        self.calls.append((query, max_results))
        self.active_requests += 1
        self.max_active_requests = max(
            self.max_active_requests,
            self.active_requests,
        )

        try:
            await asyncio.sleep(
                self.delays.get(query, 0.01)
            )

            if query in self.failing_queries:
                raise RuntimeError(
                    "Simulated search failure."
                )

            return [
                SearchResult(
                    title=f"Result for {query}",
                    url="https://example.com/result",
                    content=f"Evidence about {query}.",
                    source="fake",
                )
            ]
        finally:
            self.active_requests -= 1


def create_test_plan() -> ResearchPlan:
    """Create a deterministic plan containing three tasks."""

    return ResearchPlan(
        goal="Compare HTTP protocol behavior.",
        tasks=[
            ResearchTask(
                title="HTTP/2 reliability",
                search_query="HTTP/2 reliability features",
                rationale="Understand HTTP/2 behavior.",
            ),
            ResearchTask(
                title="HTTP/3 reliability",
                search_query="HTTP/3 reliability features",
                rationale="Understand HTTP/3 behavior.",
            ),
            ResearchTask(
                title="Protocol trade-offs",
                search_query="HTTP/2 versus HTTP/3 trade-offs",
                rationale="Compare operational trade-offs.",
            ),
        ],
    )


def test_executor_runs_tasks_concurrently() -> None:
    client = FakeSearchClient()
    executor = SearchExecutor(
        client,
        max_concurrency=2,
        max_results_per_task=3,
    )

    plan = create_test_plan()
    outcomes = asyncio.run(executor.execute(plan))

    assert [
        outcome.task.search_query
        for outcome in outcomes
    ] == [
        task.search_query
        for task in plan.tasks
    ]

    assert all(
        outcome.succeeded
        for outcome in outcomes
    )
    assert all(
        len(outcome.results) == 1
        for outcome in outcomes
    )

    assert client.max_active_requests == 2

    assert set(client.calls) == {
        ("HTTP/2 reliability features", 3),
        ("HTTP/3 reliability features", 3),
        ("HTTP/2 versus HTTP/3 trade-offs", 3),
    }


def test_executor_isolates_task_failure() -> None:
    failing_query = "HTTP/3 reliability features"

    client = FakeSearchClient(
        failing_queries={failing_query},
    )
    executor = SearchExecutor(
        client,
        max_concurrency=3,
    )

    outcomes = asyncio.run(
        executor.execute(create_test_plan())
    )

    assert outcomes[0].succeeded is True

    assert outcomes[1].succeeded is False
    assert outcomes[1].results == []
    assert outcomes[1].error == (
        "RuntimeError: Simulated search failure."
    )

    assert outcomes[2].succeeded is True


def test_executor_isolates_task_timeout() -> None:
    slow_query = "HTTP/3 reliability features"
    client = FakeSearchClient(
        delays={slow_query: 0.05},
    )
    executor = SearchExecutor(
        client,
        max_concurrency=3,
        task_timeout_seconds=0.02,
    )

    outcomes = asyncio.run(
        executor.execute(create_test_plan())
    )

    assert outcomes[0].succeeded is True
    assert outcomes[1].succeeded is False
    assert outcomes[1].results == []
    assert outcomes[1].error == (
        "TimeoutError: search exceeded 0.02 seconds."
    )
    assert outcomes[2].succeeded is True


def test_executor_rejects_invalid_concurrency() -> None:
    client = FakeSearchClient()

    with pytest.raises(
        ValueError,
        match="max_concurrency must be at least 1",
    ):
        SearchExecutor(
            client,
            max_concurrency=0,
        )


@pytest.mark.parametrize(
    "max_results_per_task",
    [0, 21],
)
def test_executor_rejects_invalid_result_limit(
    max_results_per_task: int,
) -> None:
    client = FakeSearchClient()

    with pytest.raises(
        ValueError,
        match=(
            "max_results_per_task must be "
            "between 1 and 20"
        ),
    ):
        SearchExecutor(
            client,
            max_results_per_task=max_results_per_task,
        )


@pytest.mark.parametrize(
    "task_timeout_seconds",
    [0, -1],
)
def test_executor_rejects_invalid_timeout(
    task_timeout_seconds: float,
) -> None:
    client = FakeSearchClient()

    with pytest.raises(
        ValueError,
        match=(
            "task_timeout_seconds must be greater than 0"
        ),
    ):
        SearchExecutor(
            client,
            task_timeout_seconds=task_timeout_seconds,
        )
