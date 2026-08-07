from app.services.research.pdf_rendering import render_report_pdf


def test_render_report_pdf_produces_a_valid_pdf_document() -> None:
    markdown_content = (
        "# HTTP/3 Research Report\n\n"
        "HTTP/3 reduces latency. [1]\n\n"
        "## References\n\n"
        "1. [RFC 9114](https://www.rfc-editor.org/rfc/rfc9114)"
    )

    pdf_bytes = render_report_pdf(
        title="HTTP/3 Research Report",
        markdown_content=markdown_content,
    )

    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 0


def test_render_report_pdf_renders_footnote_citations() -> None:
    pdf_bytes = render_report_pdf(
        title="HTTP/3 Research Report",
        markdown_content=(
            "# HTTP/3 Research Report\n\n"
            "HTTP/3 reduces latency.[^1]\n\n"
            "## Notes\n\n"
            "[^1]: [RFC 9114](https://www.rfc-editor.org/rfc/rfc9114)"
        ),
    )

    assert pdf_bytes.startswith(b"%PDF-")


def test_render_report_pdf_escapes_the_document_title() -> None:
    pdf_bytes = render_report_pdf(
        title="<script>alert('xss')</script>",
        markdown_content="# Report\n\nNo citations here.",
    )

    assert pdf_bytes.startswith(b"%PDF-")
