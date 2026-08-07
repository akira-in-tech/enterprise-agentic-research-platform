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


def create_web_source_id(
    url: str,
    *,
    prefix: str = "WEB",
) -> str:
    """Create a deterministic source ID from a canonical URL."""

    normalized_url = normalize_url(url)
    digest = sha256(normalized_url.encode("utf-8")).hexdigest()[:16].upper()

    return f"{prefix}-{digest}"


def build_web_source_pool(
    results: Iterable[SearchResult],
) -> list[WebSource]:
    """Build a canonical, deduplicated web source pool.

    Results are deduplicated by normalized URL rather than by source ID, so
    the same page returned by two different providers (e.g. Tavily and
    Semantic Scholar) collapses into one source. When both a paper-typed and
    a plain web-typed result share a URL, the paper version wins: it carries
    richer metadata (authors, year, venue) and its source ID uses the
    ``PAPER-`` prefix instead of ``WEB-``.
    """

    ordered_results = sorted(results, key=lambda result: result.source_type != "paper")

    seen_urls: set[str] = set()
    web_sources: list[WebSource] = []

    for result in ordered_results:
        normalized_url = normalize_url(result.url)

        if normalized_url in seen_urls:
            continue

        seen_urls.add(normalized_url)

        prefix = "PAPER" if result.source_type == "paper" else "WEB"
        source_id = create_web_source_id(normalized_url, prefix=prefix)

        web_sources.append(
            WebSource(
                source_id=source_id,
                title=result.title.strip() or "Untitled",
                url=normalized_url,
                content=result.content.strip(),
                provider=result.source.strip() or "unknown",
                source_type=result.source_type,
                authors=list(result.authors),
                year=result.year,
                venue=result.venue,
            )
        )

    return web_sources
