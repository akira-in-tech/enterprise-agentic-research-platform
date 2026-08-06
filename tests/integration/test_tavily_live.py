import pytest

from app.core.config import settings
from app.services.search.results import build_web_source_pool
from app.services.search.tavily import TavilySearchClient


@pytest.mark.integration
@pytest.mark.anyio
async def test_tavily_live_search_returns_canonical_sources() -> None:
    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    api_key = settings.tavily_api_key.get_secret_value().strip()

    if not api_key:
        pytest.fail("TAVILY_API_KEY is required for the live Tavily test.")

    client = TavilySearchClient()

    results = await client.search(
        "Python asyncio TaskGroup official documentation",
        max_results=2,
    )

    assert results
    assert len(results) <= 2

    assert all(result.url.startswith(("http://", "https://")) for result in results)

    web_sources = build_web_source_pool(results)

    assert web_sources
    assert all(source.source_id.startswith("WEB-") for source in web_sources)
    assert all(source.provider == "tavily" for source in web_sources)
