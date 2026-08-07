import asyncio
import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.services.search.semantic_scholar import SemanticScholarSearchClient


def create_test_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    payload: dict[str, Any],
    status_code: int = 200,
    api_key: str = "",
) -> tuple[SemanticScholarSearchClient, list[httpx.Request]]:
    received_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received_requests.append(request)
        return httpx.Response(status_code, content=json.dumps(payload))

    mock_transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    monkeypatch.setattr(settings, "semantic_scholar_api_key", SecretStr(api_key))
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_async_client(transport=mock_transport),
    )

    return SemanticScholarSearchClient(), received_requests


def test_search_normalizes_semantic_scholar_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, received_requests = create_test_client(
        monkeypatch,
        payload={
            "data": [
                {
                    "title": "Attention Is All You Need",
                    "url": "HTTPS://Example.COM:443/paper/attention/?utm_source=test#abstract",
                    "abstract": "The Transformer architecture relies entirely on attention.",
                    "year": 2017,
                    "authors": [{"name": "Ashish Vaswani"}, {"name": "Noam Shazeer"}],
                    "venue": "NeurIPS",
                },
                {
                    "title": "Missing URL",
                    "abstract": "This result should be skipped.",
                },
                {
                    "title": "",
                    "url": "https://example.com/no-title",
                    "abstract": "This result should be skipped too.",
                },
            ]
        },
    )

    results = asyncio.run(client.search("transformer attention", max_results=3))

    assert len(results) == 1
    result = results[0]
    assert result.title == "Attention Is All You Need"
    assert result.url == "https://example.com/paper/attention"
    assert result.content == "The Transformer architecture relies entirely on attention."
    assert result.source == "semantic_scholar"
    assert result.source_type == "paper"
    assert result.authors == ("Ashish Vaswani", "Noam Shazeer")
    assert result.year == 2017
    assert result.venue == "NeurIPS"

    assert len(received_requests) == 1
    request = received_requests[0]
    assert request.url.params["query"] == "transformer attention"
    assert request.url.params["limit"] == "3"
    assert "x-api-key" not in request.headers


def test_search_falls_back_to_open_access_pdf_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = create_test_client(
        monkeypatch,
        payload={
            "data": [
                {
                    "title": "Open Access Paper",
                    "abstract": "Available as an open-access PDF.",
                    "openAccessPdf": {"url": "https://example.com/open-access.pdf"},
                }
            ]
        },
    )

    results = asyncio.run(client.search("open access"))

    assert len(results) == 1
    assert results[0].url == "https://example.com/open-access.pdf"


def test_search_handles_missing_authors_and_year_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = create_test_client(
        monkeypatch,
        payload={
            "data": [
                {
                    "title": "No Metadata Paper",
                    "url": "https://example.com/no-metadata",
                    "abstract": "",
                }
            ]
        },
    )

    results = asyncio.run(client.search("no metadata"))

    assert len(results) == 1
    assert results[0].authors == ()
    assert results[0].year is None
    assert results[0].venue is None


def test_search_includes_api_key_header_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, received_requests = create_test_client(
        monkeypatch,
        payload={"data": []},
        api_key="test-semantic-scholar-key",
    )

    asyncio.run(client.search("HTTP"))

    assert received_requests[0].headers["x-api-key"] == "test-semantic-scholar-key"


def test_search_rejects_empty_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = create_test_client(monkeypatch, payload={"data": []})

    with pytest.raises(ValueError, match="Search query must not be empty"):
        asyncio.run(client.search("   "))


@pytest.mark.parametrize("max_results", [0, 21])
def test_search_rejects_invalid_max_results(
    monkeypatch: pytest.MonkeyPatch,
    max_results: int,
) -> None:
    client, _ = create_test_client(monkeypatch, payload={"data": []})

    with pytest.raises(ValueError, match="max_results must be between 1 and 20"):
        asyncio.run(client.search("HTTP", max_results=max_results))


def test_client_does_not_require_an_api_key() -> None:
    """Semantic Scholar's public API works unauthenticated, unlike Tavily's."""

    SemanticScholarSearchClient()


def test_search_raises_for_non_2xx_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = create_test_client(monkeypatch, payload={}, status_code=503)

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(client.search("HTTP"))


def test_search_returns_empty_list_for_empty_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = create_test_client(monkeypatch, payload={"data": []})

    results = asyncio.run(client.search("Linux epoll behavior"))

    assert results == []
