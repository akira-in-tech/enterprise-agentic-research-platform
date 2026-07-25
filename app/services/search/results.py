from collections.abc import Iterable
from hashlib import sha256

from app.schemas.source import WebSource
from app.services.search.base import SearchResult
from app.services.search.urls import normalize_url


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


def create_web_source_id(url: str) -> str:
    """Create a deterministic source ID from a canonical URL."""

    normalized_url = normalize_url(url)
    digest = sha256(
        normalized_url.encode("utf-8")
    ).hexdigest()[:16].upper()

    return f"WEB-{digest}"


def build_web_source_pool(
    results: Iterable[SearchResult],
) -> list[WebSource]:
    """Build a canonical, deduplicated web source pool."""

    seen_source_ids: set[str] = set()
    web_sources: list[WebSource] = []

    for result in results:
        normalized_url = normalize_url(result.url)
        source_id = create_web_source_id(
            normalized_url
        )

        if source_id in seen_source_ids:
            continue

        seen_source_ids.add(source_id)

        web_sources.append(
            WebSource(
                source_id=source_id,
                title=result.title.strip() or "Untitled",
                url=normalized_url,
                content=result.content.strip(),
                provider=result.source.strip() or "unknown",
            )
        )

    return web_sources