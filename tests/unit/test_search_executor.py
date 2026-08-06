import asyncio

import httpx
import pytest

from app.core.circuit_breaker import CircuitBreaker
from app.schemas.planner import (
    ReportSection,
    ResearchPlan,
    ResearchTask,
)
from app.services.search.base import SearchResult
from app.services.search.executor import SearchExecutor


class FlakySearchClient:
    """Fail with a given error a fixed number of times, then succeed."""

    def __init__(
        self,
        *,
        failures: int,
        error: Exception,
    ) -> None:
        self.failures = failures
        self.error = error
        self.calls = 0

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
    ) -> list[SearchResult]:
        self.calls += 1

        if self.calls <= self.failures:
            raise self.error

        return [
            SearchResult(
                title=f"Result for {query}",
                url="https://example.com/result",
                content=f"Evidence about {query}.",
                source="fake",
            )
        ]


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
            await asyncio.sleep(self.delays.get(query, 0.01))

            if query in self.failing_queries:
                raise RuntimeError("Simulated search failure.")

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
        sub_questions=[
            "What reliability features does HTTP/2 provide?",
            "What reliability features does HTTP/3 provide?",
            "What are their operational trade-offs?",
        ],
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
        report_outline=[
            ReportSection(
                title="Technical Background",
                purpose="Explain the foundations of HTTP/2 and HTTP/3.",
            ),
            ReportSection(
                title="Reliability",
                purpose="Compare protocol reliability behavior.",
            ),
            ReportSection(
                title="Operational Trade-offs",
                purpose="Compare production deployment considerations.",
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

    assert [outcome.task.search_query for outcome in outcomes] == [
        task.search_query for task in plan.tasks
    ]

    assert all(outcome.succeeded for outcome in outcomes)
    assert all(len(outcome.results) == 1 for outcome in outcomes)

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

    outcomes = asyncio.run(executor.execute(create_test_plan()))

    assert outcomes[0].succeeded is True

    assert outcomes[1].succeeded is False
    assert outcomes[1].results == []
    assert outcomes[1].error == ("RuntimeError: Simulated search failure.")

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

    outcomes = asyncio.run(executor.execute(create_test_plan()))

    assert outcomes[0].succeeded is True
    assert outcomes[1].succeeded is False
    assert outcomes[1].results == []
    assert outcomes[1].error == ("TimeoutError: search exceeded 0.02 seconds.")
    assert outcomes[2].succeeded is True


def test_executor_circuit_breaker_stops_calling_after_threshold() -> None:
    client = FakeSearchClient(
        failing_queries={
            "HTTP/2 reliability features",
            "HTTP/3 reliability features",
            "HTTP/2 versus HTTP/3 trade-offs",
        },
    )
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout_seconds=60)
    executor = SearchExecutor(
        client,
        max_concurrency=1,
        circuit_breaker=breaker,
    )

    outcomes = asyncio.run(executor.execute(create_test_plan()))

    assert outcomes[0].error == "RuntimeError: Simulated search failure."
    assert outcomes[1].error == "RuntimeError: Simulated search failure."
    assert outcomes[2].succeeded is False
    assert outcomes[2].error is not None
    assert "CircuitBreakerOpenError" in outcomes[2].error
    # The third task never reached the search client: the breaker opened
    # after the second consecutive failure and rejected the call locally.
    assert len(client.calls) == 2


def test_executor_retries_a_transient_transport_error() -> None:
    client = FlakySearchClient(
        failures=1,
        error=httpx.ConnectError("Connection refused."),
    )
    executor = SearchExecutor(
        client,
        max_concurrency=1,
    )

    outcomes = asyncio.run(
        executor.execute_tasks(create_test_plan().tasks[:1]),
    )

    assert outcomes[0].succeeded is True
    assert client.calls == 2


def test_executor_does_not_retry_a_non_transient_error() -> None:
    client = FlakySearchClient(
        failures=1,
        error=RuntimeError("Simulated search failure."),
    )
    executor = SearchExecutor(
        client,
        max_concurrency=1,
    )

    outcomes = asyncio.run(
        executor.execute_tasks(create_test_plan().tasks[:1]),
    )

    assert outcomes[0].succeeded is False
    assert client.calls == 1


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
        match=("max_results_per_task must be between 1 and 20"),
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
        match=("task_timeout_seconds must be greater than 0"),
    ):
        SearchExecutor(
            client,
            task_timeout_seconds=task_timeout_seconds,
        )
