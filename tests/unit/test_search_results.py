from app.services.search.base import SearchResult
from app.services.search.results import (
    build_web_source_pool,
    create_web_source_id,
    deduplicate_search_results,
)


def test_deduplicate_search_results_preserves_first_result() -> None:
    first_result = SearchResult(
        title="RFC 9114",
        url="https://www.rfc-editor.org/rfc/rfc9114",
        content="HTTP/3 protocol specification.",
        source="tavily",
    )
    duplicate_result = SearchResult(
        title="HTTP/3 RFC",
        url="https://www.rfc-editor.org/rfc/rfc9114",
        content="A duplicate representation of the same source.",
        source="tavily",
    )
    second_result = SearchResult(
        title="QUIC RFC",
        url="https://www.rfc-editor.org/rfc/rfc9000",
        content="QUIC transport protocol specification.",
        source="tavily",
    )

    results = deduplicate_search_results(
        [
            first_result,
            duplicate_result,
            second_result,
        ]
    )

    assert results == [
        first_result,
        second_result,
    ]


def test_deduplicate_search_results_accepts_empty_input() -> None:
    assert deduplicate_search_results([]) == []


def test_create_web_source_id_is_stable() -> None:
    first_id = create_web_source_id(
        "HTTPS://Example.COM:443/docs/"
        "?utm_source=newsletter#section"
    )
    second_id = create_web_source_id(
        "https://example.com/docs"
    )

    assert first_id == second_id
    assert first_id.startswith("WEB-")
    assert len(first_id) == 20


def test_build_web_source_pool_assigns_ids_and_deduplicates() -> None:
    results = [
        SearchResult(
            title="HTTP Semantics",
            url=(
                "https://www.rfc-editor.org/rfc/rfc9110"
                "?utm_source=test"
            ),
            content="HTTP semantics specification.",
            source="tavily",
        ),
        SearchResult(
            title="Duplicate HTTP Semantics",
            url="https://www.rfc-editor.org/rfc/rfc9110",
            content="Duplicate representation.",
            source="tavily",
        ),
        SearchResult(
            title="HTTP/3",
            url="https://www.rfc-editor.org/rfc/rfc9114",
            content="HTTP/3 specification.",
            source="tavily",
        ),
    ]

    web_sources = build_web_source_pool(results)

    assert len(web_sources) == 2

    assert web_sources[0].source_id == create_web_source_id(
        "https://www.rfc-editor.org/rfc/rfc9110"
    )
    assert web_sources[0].title == "HTTP Semantics"
    assert web_sources[0].url == (
        "https://www.rfc-editor.org/rfc/rfc9110"
    )
    assert web_sources[0].provider == "tavily"

    assert web_sources[1].source_id == create_web_source_id(
        "https://www.rfc-editor.org/rfc/rfc9114"
    )