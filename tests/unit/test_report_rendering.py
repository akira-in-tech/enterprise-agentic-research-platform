from app.schemas.report import ResearchReportSourceResponse
from app.services.research.report_rendering import render_report_content


def create_source(
    *,
    source_id: str,
    title: str = "HTTP/3 and QUIC",
    source_type: str = "web",
    authors: list[str] | None = None,
    year: int | None = None,
) -> ResearchReportSourceResponse:
    return ResearchReportSourceResponse(
        source_id=source_id,
        origin="web",
        title=title,
        locator=f"https://example.com/{source_id}",
        provider="fixture",
        relevance=0.9,
        content_quality=0.8,
        traceability=1.0,
        overall_score=0.85,
        cited=True,
        source_type=source_type,  # type: ignore[arg-type]
        authors=authors or [],
        year=year,
    )


def test_numbered_style_rewrites_markers_and_appends_a_references_list() -> None:
    sources = [
        create_source(source_id="WEB-0000000000000001"),
        create_source(
            source_id="PAPER-0000000000000002",
            source_type="paper",
            authors=["Ada Lovelace"],
            year=1843,
        ),
    ]
    content = (
        "HTTP/3 reduces latency. [WEB-0000000000000001]\n\n"
        "The analytical engine predates modern computing. [PAPER-0000000000000002]"
    )

    rendered = render_report_content(content=content, sources=sources, style="numbered")

    assert "[1]" in rendered
    assert "[2]" in rendered
    assert "## References" in rendered
    assert "1. [HTTP/3 and QUIC](https://example.com/WEB-0000000000000001)" in rendered
    assert (
        "2. [HTTP/3 and QUIC](https://example.com/PAPER-0000000000000002) (Lovelace, 1843)"
        in rendered
    )


def test_footnote_style_rewrites_markers_and_appends_a_notes_list() -> None:
    sources = [create_source(source_id="WEB-0000000000000001")]
    content = "HTTP/3 reduces latency. [WEB-0000000000000001]"

    rendered = render_report_content(content=content, sources=sources, style="footnote")

    assert "[^1]" in rendered
    assert "## Notes" in rendered
    assert "[^1]: [HTTP/3 and QUIC](https://example.com/WEB-0000000000000001)" in rendered


def test_multiple_authors_are_summarized_with_et_al() -> None:
    sources = [
        create_source(
            source_id="PAPER-0000000000000002",
            source_type="paper",
            authors=["Ada Lovelace", "Charles Babbage"],
            year=1843,
        )
    ]
    content = "The analytical engine predates modern computing. [PAPER-0000000000000002]"

    rendered = render_report_content(content=content, sources=sources, style="numbered")

    assert "(Lovelace et al., 1843)" in rendered


def test_web_sources_get_no_author_year_suffix() -> None:
    sources = [create_source(source_id="WEB-0000000000000001")]
    content = "HTTP/3 reduces latency. [WEB-0000000000000001]"

    rendered = render_report_content(content=content, sources=sources, style="numbered")

    assert "1. [HTTP/3 and QUIC](https://example.com/WEB-0000000000000001)\n" in rendered + "\n"


def test_repeated_citations_of_the_same_source_share_one_reference_entry() -> None:
    sources = [create_source(source_id="WEB-0000000000000001")]
    content = (
        "First claim. [WEB-0000000000000001]\n\n"
        "Second claim citing the same source. [WEB-0000000000000001]"
    )

    rendered = render_report_content(content=content, sources=sources, style="numbered")

    assert rendered.count("1. [HTTP/3 and QUIC]") == 1


def test_unknown_citation_markers_are_left_untouched() -> None:
    sources: list[ResearchReportSourceResponse] = []
    content = "An unverifiable claim. [WEB-FFFFFFFFFFFFFFFF]"

    rendered = render_report_content(content=content, sources=sources, style="numbered")

    assert rendered == content
    assert "## References" not in rendered


def test_content_with_no_citations_is_returned_unchanged() -> None:
    sources = [create_source(source_id="WEB-0000000000000001")]
    content = "No citations here at all."

    rendered = render_report_content(content=content, sources=sources, style="numbered")

    assert rendered == content


def test_reference_numbers_follow_source_list_order_not_first_appearance() -> None:
    sources = [
        create_source(source_id="WEB-0000000000000001", title="First in list"),
        create_source(source_id="WEB-0000000000000002", title="Second in list"),
    ]
    # The second source in the list is cited first in the text.
    content = (
        "Cites the second source first. [WEB-0000000000000002]\n\n"
        "Cites the first source second. [WEB-0000000000000001]"
    )

    rendered = render_report_content(content=content, sources=sources, style="numbered")

    assert "Cites the second source first. [2]" in rendered
    assert "Cites the first source second. [1]" in rendered
    references_section = rendered.split("## References")[1]
    assert references_section.index("1. [First in list]") < references_section.index(
        "2. [Second in list]"
    )
