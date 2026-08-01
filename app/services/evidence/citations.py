import re
from collections.abc import Iterable

from app.schemas.evidence import CitationAudit, EvidenceSource

CITATION_PATTERN = re.compile(r"\[((?:WEB|PRIVATE|MCP)-[0-9A-F]{16})\]")


class CitationValidator:
    """Validate source references and paragraph-level citation coverage."""

    def validate(
        self,
        *,
        report: str,
        sources: Iterable[EvidenceSource],
    ) -> CitationAudit:
        """Return deterministic citation integrity and coverage findings."""

        normalized_report = report.strip()

        if not normalized_report:
            raise ValueError("report must not be empty.")

        known_source_ids = {source.source_id for source in sources}
        cited_source_ids = list(dict.fromkeys(CITATION_PATTERN.findall(normalized_report)))
        unknown_source_ids = [
            source_id for source_id in cited_source_ids if source_id not in known_source_ids
        ]
        claim_paragraphs = self._claim_paragraphs(normalized_report)
        uncited_claims = [
            paragraph for paragraph in claim_paragraphs if not CITATION_PATTERN.search(paragraph)
        ]
        covered_count = len(claim_paragraphs) - len(uncited_claims)
        coverage_ratio = covered_count / len(claim_paragraphs) if claim_paragraphs else 1.0

        return CitationAudit(
            valid=not unknown_source_ids and not uncited_claims and bool(cited_source_ids),
            cited_source_ids=cited_source_ids,
            unknown_source_ids=unknown_source_ids,
            uncited_claims=uncited_claims,
            coverage_ratio=round(coverage_ratio, 4),
        )

    @staticmethod
    def _claim_paragraphs(report: str) -> list[str]:
        paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", report)]

        return [
            paragraph
            for paragraph in paragraphs
            if len(paragraph) >= 20
            and not paragraph.startswith("#")
            and not paragraph.lower().startswith("sources:")
        ]
