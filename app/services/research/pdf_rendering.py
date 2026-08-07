from html import escape

REPORT_PDF_CSS = """
@page {
    size: A4;
    margin: 2.4cm 2cm;
    @bottom-center {
        content: counter(page) " / " counter(pages);
        font-family: "DejaVu Sans", sans-serif;
        font-size: 9pt;
        color: #858981;
    }
}

body {
    font-family: "DejaVu Serif", "Liberation Serif", serif;
    color: #171916;
    background: #fbfaf6;
    font-size: 11pt;
    line-height: 1.55;
}

h1, h2, h3, h4 {
    font-family: "DejaVu Serif", "Liberation Serif", serif;
    color: #244a1a;
    line-height: 1.25;
}

h1 {
    font-size: 22pt;
    border-bottom: 2pt solid #315f24;
    padding-bottom: 0.2cm;
    margin-bottom: 0.6cm;
}

h2 {
    font-size: 15pt;
    margin-top: 0.9cm;
}

h3 {
    font-size: 12.5pt;
}

a {
    color: #315f24;
    text-decoration: none;
}

p {
    margin: 0.3cm 0;
}

hr {
    border: none;
    border-top: 1pt solid #dedfd8;
    margin: 0.6cm 0;
}

code, pre {
    font-family: "DejaVu Sans Mono", "Liberation Mono", monospace;
    font-size: 9.5pt;
    background: #f3f2ed;
}

pre {
    padding: 0.3cm;
    white-space: pre-wrap;
}

table {
    border-collapse: collapse;
    width: 100%;
    margin: 0.4cm 0;
}

th, td {
    border: 1pt solid #dedfd8;
    padding: 0.15cm 0.25cm;
    text-align: left;
}

sup {
    color: #315f24;
}

.footnote, .footnotes {
    font-size: 9pt;
    color: #5f625d;
}
"""


def render_report_pdf(*, title: str, markdown_content: str) -> bytes:
    """Render a Markdown report into a branded PDF document.

    The ``footnotes`` extension is required for ``[^1]``-style footnote
    citations to be parsed into real superscript links; without it they
    would pass through as literal text.

    ``markdown`` and ``weasyprint`` are imported lazily so that importing
    this module (e.g. transitively through the API app) doesn't require
    WeasyPrint's native libraries to be loadable unless a PDF is actually
    being rendered.
    """

    import markdown  # type: ignore[import-untyped]
    from weasyprint import HTML  # type: ignore[import-untyped]

    html_body = markdown.markdown(
        markdown_content,
        extensions=["footnotes", "tables"],
    )
    html_document = (
        "<!doctype html>"
        "<html><head><meta charset=\"utf-8\">"
        f"<title>{escape(title)}</title>"
        f"<style>{REPORT_PDF_CSS}</style>"
        f"</head><body>{html_body}</body></html>"
    )

    pdf_bytes: bytes = HTML(string=html_document).write_pdf()
    return pdf_bytes
