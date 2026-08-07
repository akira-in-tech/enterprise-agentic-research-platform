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
    first_id = create_web_source_id("HTTPS://Example.COM:443/docs/?utm_source=newsletter#section")
    second_id = create_web_source_id("https://example.com/docs")

    assert first_id == second_id
    assert first_id.startswith("WEB-")
    assert len(first_id) == 20


def test_build_web_source_pool_assigns_ids_and_deduplicates() -> None:
    results = [
        SearchResult(
            title="HTTP Semantics",
            url=("https://www.rfc-editor.org/rfc/rfc9110?utm_source=test"),
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
    assert web_sources[0].url == ("https://www.rfc-editor.org/rfc/rfc9110")
    assert web_sources[0].provider == "tavily"

    assert web_sources[1].source_id == create_web_source_id(
        "https://www.rfc-editor.org/rfc/rfc9114"
    )


def test_create_web_source_id_accepts_a_custom_prefix() -> None:
    paper_id = create_web_source_id(
        "https://example.com/paper/attention",
        prefix="PAPER",
    )

    assert paper_id.startswith("PAPER-")
    assert len(paper_id) == 22


def test_build_web_source_pool_prefers_the_paper_version_of_a_shared_url() -> None:
    shared_url = "https://example.com/paper/attention"
    web_result = SearchResult(
        title="Attention Is All You Need (blog summary)",
        url=shared_url,
        content="A blog summary of the paper.",
        source="tavily",
    )
    paper_result = SearchResult(
        title="Attention Is All You Need",
        url=shared_url,
        content="The original paper abstract.",
        source="semantic_scholar",
        source_type="paper",
        authors=("Ashish Vaswani",),
        year=2017,
        venue="NeurIPS",
    )

    web_sources = build_web_source_pool([web_result, paper_result])

    assert len(web_sources) == 1
    source = web_sources[0]
    assert source.source_id.startswith("PAPER-")
    assert source.title == "Attention Is All You Need"
    assert source.source_type == "paper"
    assert source.authors == ["Ashish Vaswani"]
    assert source.year == 2017
    assert source.venue == "NeurIPS"


def test_build_web_source_pool_keeps_distinct_urls_across_providers() -> None:
    results = [
        SearchResult(
            title="Blog post",
            url="https://example.com/blog/http3",
            content="A blog post about HTTP/3.",
            source="tavily",
        ),
        SearchResult(
            title="HTTP/3 Performance Paper",
            url="https://example.com/paper/http3-performance",
            content="A paper measuring HTTP/3 performance.",
            source="semantic_scholar",
            source_type="paper",
            authors=("Jane Doe",),
            year=2022,
        ),
    ]

    web_sources = build_web_source_pool(results)

    assert len(web_sources) == 2
    assert {source.source_type for source in web_sources} == {"web", "paper"}
    assert sum(1 for source in web_sources if source.source_id.startswith("PAPER-")) == 1
    assert sum(1 for source in web_sources if source.source_id.startswith("WEB-")) == 1
