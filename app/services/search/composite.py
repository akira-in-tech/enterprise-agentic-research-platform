import asyncio
import logging

from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from app.services.search.base import SearchClient, SearchResult

logger = logging.getLogger(__name__)


class AcademicAwareSearchClient:
    """Fan out to a general web client and an academic client.

    Each leg fails open independently: a Semantic Scholar outage never
    breaks Tavily results, and vice versa. The academic leg carries its own
    circuit breaker so a persistently failing provider doesn't eat a fresh
    HTTP timeout on every single research task.
    """

    def __init__(
        self,
        *,
        web_client: SearchClient,
        academic_client: SearchClient,
        academic_circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._web_client = web_client
        self._academic_client = academic_client
        self._academic_circuit_breaker = academic_circuit_breaker

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
    ) -> list[SearchResult]:
        """Search both providers concurrently and merge the results."""

        web_results, academic_results = await asyncio.gather(
            self._search_web(query, max_results=max_results),
            self._search_academic(query, max_results=max_results),
        )

        return [*web_results, *academic_results]

    async def _search_web(
        self,
        query: str,
        *,
        max_results: int,
    ) -> list[SearchResult]:
        try:
            return await self._web_client.search(query, max_results=max_results)
        except Exception:
            logger.exception("Web search leg failed; continuing with academic results only.")
            return []

    async def _search_academic(
        self,
        query: str,
        *,
        max_results: int,
    ) -> list[SearchResult]:
        async def run() -> list[SearchResult]:
            return await self._academic_client.search(query, max_results=max_results)

        try:
            if self._academic_circuit_breaker is not None:
                return await self._academic_circuit_breaker.call(run)

            return await run()
        except CircuitBreakerOpenError:
            logger.info("Academic search circuit open; skipping Semantic Scholar this call.")
            return []
        except Exception:
            logger.exception("Academic search leg failed; continuing with web results only.")
            return []
