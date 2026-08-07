from typing import Any, cast

import httpx

from app.core.config import settings
from app.services.search.base import SearchResult
from app.services.search.urls import normalize_url

SEMANTIC_SCHOLAR_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
SEMANTIC_SCHOLAR_FIELDS = "title,abstract,url,year,authors,venue,externalIds,openAccessPdf"
_REQUEST_TIMEOUT_SECONDS = 10.0


class SemanticScholarSearchClient:
    """Search Semantic Scholar's Academic Graph API for scholarly papers."""

    def __init__(self) -> None:
        api_key = settings.semantic_scholar_api_key.get_secret_value().strip()
        self._api_key = api_key or None

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
    ) -> list[SearchResult]:
        """Search Semantic Scholar and normalize its provider-specific response."""

        normalized_query = query.strip()

        if not normalized_query:
            raise ValueError("Search query must not be empty.")

        if not 1 <= max_results <= 20:
            raise ValueError("max_results must be between 1 and 20.")

        headers = {"x-api-key": self._api_key} if self._api_key else {}
        params: dict[str, str | int] = {
            "query": normalized_query,
            "limit": max_results,
            "fields": SEMANTIC_SCHOLAR_FIELDS,
        }

        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                SEMANTIC_SCHOLAR_SEARCH_URL,
                params=params,
                headers=headers,
            )
            response.raise_for_status()
            payload = cast(dict[str, Any], response.json())

        raw_results = cast(list[dict[str, Any]], payload.get("data", []))

        results: list[SearchResult] = []

        for item in raw_results:
            raw_url = str(
                item.get("url") or (item.get("openAccessPdf") or {}).get("url") or ""
            ).strip()
            title = str(item.get("title") or "").strip()

            if not raw_url or not title:
                continue

            try:
                url = normalize_url(raw_url)
            except ValueError:
                continue

            authors = tuple(
                author_name
                for author in cast(list[dict[str, Any]], item.get("authors") or [])
                if (author_name := str(author.get("name") or "").strip())
            )
            raw_year = item.get("year")
            year = raw_year if isinstance(raw_year, int) else None

            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    content=str(item.get("abstract") or "").strip(),
                    source="semantic_scholar",
                    source_type="paper",
                    authors=authors,
                    year=year,
                    venue=(str(item.get("venue") or "").strip() or None),
                )
            )

        return results
