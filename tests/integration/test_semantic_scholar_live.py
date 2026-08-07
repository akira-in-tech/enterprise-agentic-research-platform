import httpx
import pytest

from app.core.config import settings
from app.services.search.results import build_web_source_pool
from app.services.search.semantic_scholar import SemanticScholarSearchClient


@pytest.mark.integration
@pytest.mark.anyio
async def test_semantic_scholar_live_search_returns_canonical_sources() -> None:
    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    client = SemanticScholarSearchClient()

    try:
        results = await client.search(
            "transformer attention mechanism",
            max_results=2,
        )
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 429:
            pytest.skip("Semantic Scholar rate-limited this run.")
        raise

    assert results
    assert len(results) <= 2
    assert all(result.url.startswith(("http://", "https://")) for result in results)
    assert all(result.source_type == "paper" for result in results)

    web_sources = build_web_source_pool(results)

    assert web_sources
    assert all(source.source_id.startswith("PAPER-") for source in web_sources)
    assert all(source.provider == "semantic_scholar" for source in web_sources)
    assert all(source.source_type == "paper" for source in web_sources)
