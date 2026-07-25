import asyncio
from typing import Any

import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.services.search import tavily as tavily_module
from app.services.search.tavily import TavilySearchClient


class FakeAsyncTavilyClient:
    """Replace the real Tavily SDK during unit tests."""

    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.received_arguments: dict[str, Any] = {}

    async def search(self, **kwargs: Any) -> dict[str, Any]:
        self.received_arguments = kwargs
        return self.response


def create_test_client(
    monkeypatch: pytest.MonkeyPatch,
    response: dict[str, Any],
) -> tuple[TavilySearchClient, FakeAsyncTavilyClient]:
    fake_sdk_client = FakeAsyncTavilyClient(response)

    monkeypatch.setattr(
        settings,
        "tavily_api_key",
        SecretStr("test-api-key"),
    )
    monkeypatch.setattr(
        tavily_module,
        "AsyncTavilyClient",
        lambda api_key: fake_sdk_client,
    )

    return TavilySearchClient(), fake_sdk_client


def test_search_normalizes_tavily_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, fake_sdk_client = create_test_client(
        monkeypatch,
        {
            "results": [
                {
                    "title": "HTTP PUT",
                    "url": (
                        "HTTPS://Example.COM:443/http-put/"
                        "?utm_source=test#semantics"
                    ),
                    "content": "PUT is an idempotent HTTP method.",
                },
                {
                    "title": "Unsupported URL",
                    "url": "ftp://example.com/http-put",
                    "content": "This result should be skipped.",
                },
                {
                    "title": "Missing URL",
                    "url": "",
                    "content": "This result should be skipped.",
                },
            ]
        },
    )

    results = asyncio.run(
        client.search(
            "HTTP PUT idempotency",
            max_results=3,
        )
    )

    assert len(results) == 1
    assert results[0].title == "HTTP PUT"
    assert results[0].url == "https://example.com/http-put"
    assert results[0].content == "PUT is an idempotent HTTP method."
    assert results[0].source == "tavily"

    assert fake_sdk_client.received_arguments == {
        "query": "HTTP PUT idempotency",
        "search_depth": "basic",
        "max_results": 3,
        "include_answer": False,
        "include_raw_content": False,
        "include_images": False,
    }


def test_search_rejects_empty_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = create_test_client(
        monkeypatch,
        {"results": []},
    )

    with pytest.raises(
        ValueError,
        match="Search query must not be empty",
    ):
        asyncio.run(client.search("   "))


@pytest.mark.parametrize("max_results", [0, 21])
def test_search_rejects_invalid_max_results(
    monkeypatch: pytest.MonkeyPatch,
    max_results: int,
) -> None:
    client, _ = create_test_client(
        monkeypatch,
        {"results": []},
    )

    with pytest.raises(
        ValueError,
        match="max_results must be between 1 and 20",
    ):
        asyncio.run(
            client.search(
                "HTTP",
                max_results=max_results,
            )
        )


def test_client_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "tavily_api_key",
        SecretStr(""),
    )

    with pytest.raises(
        ValueError,
        match="TAVILY_API_KEY must not be empty",
    ):
        TavilySearchClient()


def test_search_returns_empty_list_for_empty_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = create_test_client(
        monkeypatch,
        {"results": []},
    )

    results = asyncio.run(
        client.search("Linux epoll behavior")
    )

    assert results == []
