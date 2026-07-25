from app.services.search.base import SearchResult
from app.services.search.results import (
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