from typing import Any, cast

from tavily import AsyncTavilyClient  # type: ignore[import-untyped]

from app.core.config import settings
from app.services.search.base import SearchResult
from app.services.search.urls import normalize_url


class TavilySearchClient:
    """Search the public web through Tavily."""

    def __init__(self) -> None:
        api_key = settings.tavily_api_key.get_secret_value().strip()

        if not api_key:
            raise ValueError("TAVILY_API_KEY must not be empty.")

        self._client = AsyncTavilyClient(api_key=api_key)

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
    ) -> list[SearchResult]:
        """Search Tavily and normalize its provider-specific response."""

        normalized_query = query.strip()

        if not normalized_query:
            raise ValueError("Search query must not be empty.")

        if not 1 <= max_results <= 20:
            raise ValueError(
                "max_results must be between 1 and 20."
            )

        response = cast(
            dict[str, Any],
            await self._client.search(
                query=normalized_query,
                search_depth="basic",
                max_results=max_results,
                include_answer=False,
                include_raw_content=False,
                include_images=False,
            ),
        )

        raw_results = cast(
            list[dict[str, Any]],
            response.get("results", []),
        )

        results: list[SearchResult] = []

        for item in raw_results:
            raw_url = str(
                item.get("url") or ""
            ).strip()

            try:
                url = normalize_url(raw_url)
            except ValueError:
                continue

            results.append(
                SearchResult(
                    title=str(
                        item.get("title") or "Untitled"
                    ).strip(),
                    url=url,
                    content=str(
                        item.get("content") or ""
                    ).strip(),
                    source="tavily",
                )
            )

        return results