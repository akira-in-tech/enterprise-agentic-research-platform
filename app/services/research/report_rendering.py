import re
from collections.abc import Sequence
from typing import Literal

from app.schemas.report import ResearchReportSourceResponse
from app.services.evidence.citations import CITATION_PATTERN

CitationStyle = Literal["numbered", "footnote"]


def render_report_content(
    *,
    content: str,
    sources: Sequence[ResearchReportSourceResponse],
    style: CitationStyle,
) -> str:
    """Rewrite inline citation markers and append a References/Notes list.

    Citation numbers reuse the position of each source within ``sources``
    (1-indexed), matching the frontend's ``sourceIndexById`` scheme exactly
    so a report viewed on the web page and one downloaded as a file cite
    the same source under the same number.
    """

    index_by_source_id = {
        source.source_id: position + 1 for position, source in enumerate(sources)
    }
    source_by_id = {source.source_id: source for source in sources}
    cited_source_ids: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        source_id = match.group(1)
        number = index_by_source_id.get(source_id)

        if number is None:
            return match.group(0)

        cited_source_ids.add(source_id)

        if style == "numbered":
            return f"[{number}]"

        return f"[^{number}]"

    rewritten = CITATION_PATTERN.sub(replace, content.strip())

    if not cited_source_ids:
        return rewritten

    ordered_source_ids = sorted(
        cited_source_ids, key=lambda source_id: index_by_source_id[source_id]
    )
    heading = "## References" if style == "numbered" else "## Notes"
    lines = [heading, ""]

    for source_id in ordered_source_ids:
        source = source_by_id[source_id]
        number = index_by_source_id[source_id]
        marker = f"{number}." if style == "numbered" else f"[^{number}]:"
        lines.append(f"{marker} [{source.title}]({source.locator}){_format_citation(source)}")

    return f"{rewritten}\n\n" + "\n".join(lines)


def _format_citation(source: ResearchReportSourceResponse) -> str:
    """Format a short author/year suffix for paper sources, e.g. ' (Smith et al., 2023)'."""

    if source.source_type != "paper" or not source.authors:
        return ""

    first_author_last_name = source.authors[0].split()[-1]
    suffix = " et al." if len(source.authors) > 1 else ""
    year = f", {source.year}" if source.year is not None else ""

    return f" ({first_author_last_name}{suffix}{year})"
