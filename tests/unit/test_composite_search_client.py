import asyncio

from app.core.circuit_breaker import CircuitBreaker
from app.services.search.base import SearchResult
from app.services.search.composite import AcademicAwareSearchClient


class RecordingSearchClient:
    def __init__(
        self,
        *,
        results: list[SearchResult] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.results = results or []
        self.error = error
        self.calls: list[tuple[str, int]] = []

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        self.calls.append((query, max_results))

        if self.error is not None:
            raise self.error

        return self.results


def create_web_result(title: str) -> SearchResult:
    return SearchResult(
        title=title,
        url=f"https://example.com/{title}",
        content="Web content.",
        source="tavily",
    )


def create_paper_result(title: str) -> SearchResult:
    return SearchResult(
        title=title,
        url=f"https://example.com/paper/{title}",
        content="Paper abstract.",
        source="semantic_scholar",
        source_type="paper",
    )


def test_search_merges_results_from_both_providers() -> None:
    web_client = RecordingSearchClient(results=[create_web_result("web-1")])
    academic_client = RecordingSearchClient(results=[create_paper_result("paper-1")])
    client = AcademicAwareSearchClient(web_client=web_client, academic_client=academic_client)

    results = asyncio.run(client.search("HTTP/3", max_results=5))

    assert len(results) == 2
    assert {result.source for result in results} == {"tavily", "semantic_scholar"}
    assert web_client.calls == [("HTTP/3", 5)]
    assert academic_client.calls == [("HTTP/3", 5)]


def test_academic_leg_failure_does_not_affect_web_results() -> None:
    web_client = RecordingSearchClient(results=[create_web_result("web-1")])
    academic_client = RecordingSearchClient(error=RuntimeError("Semantic Scholar is down."))
    client = AcademicAwareSearchClient(web_client=web_client, academic_client=academic_client)

    results = asyncio.run(client.search("HTTP/3"))

    assert len(results) == 1
    assert results[0].source == "tavily"


def test_web_leg_failure_does_not_affect_academic_results() -> None:
    web_client = RecordingSearchClient(error=RuntimeError("Tavily is down."))
    academic_client = RecordingSearchClient(results=[create_paper_result("paper-1")])
    client = AcademicAwareSearchClient(web_client=web_client, academic_client=academic_client)

    results = asyncio.run(client.search("HTTP/3"))

    assert len(results) == 1
    assert results[0].source == "semantic_scholar"


def test_both_legs_failing_returns_an_empty_list_without_raising() -> None:
    web_client = RecordingSearchClient(error=RuntimeError("Tavily is down."))
    academic_client = RecordingSearchClient(error=RuntimeError("Semantic Scholar is down."))
    client = AcademicAwareSearchClient(web_client=web_client, academic_client=academic_client)

    results = asyncio.run(client.search("HTTP/3"))

    assert results == []


def test_repeated_academic_failures_open_the_inner_circuit_breaker() -> None:
    web_client = RecordingSearchClient(results=[create_web_result("web-1")])
    academic_client = RecordingSearchClient(error=RuntimeError("Semantic Scholar is down."))
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout_seconds=60)
    client = AcademicAwareSearchClient(
        web_client=web_client,
        academic_client=academic_client,
        academic_circuit_breaker=breaker,
    )

    asyncio.run(client.search("HTTP/3"))
    asyncio.run(client.search("HTTP/3"))

    # The first call reaches the academic client and opens the breaker; the
    # second call is rejected locally by the (now open) breaker.
    assert len(academic_client.calls) == 1
