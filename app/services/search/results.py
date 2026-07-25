from collections.abc import Iterable

from app.services.search.base import SearchResult


def deduplicate_search_results(
    results: Iterable[SearchResult],
) -> list[SearchResult]:
    """Deduplicate canonical search results by URL."""

    seen_urls: set[str] = set()
    unique_results: list[SearchResult] = []

    for result in results:
        if result.url in seen_urls:
            continue

        seen_urls.add(result.url)
        unique_results.append(result)

    return unique_results