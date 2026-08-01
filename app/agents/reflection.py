from collections.abc import Sequence

from app.schemas.evidence import CitationAudit, EvidenceScore, ReflectionDecision


class ReflectionAgent:
    """Apply a deterministic quality gate to an analyst report."""

    def __init__(
        self,
        *,
        minimum_evidence_count: int = 2,
        minimum_average_score: float = 0.25,
    ) -> None:
        if minimum_evidence_count < 1:
            raise ValueError("minimum_evidence_count must be at least 1.")

        if not 0.0 <= minimum_average_score <= 1.0:
            raise ValueError("minimum_average_score must be between 0 and 1.")

        self._minimum_evidence_count = minimum_evidence_count
        self._minimum_average_score = minimum_average_score

    def review(
        self,
        *,
        citation_audit: CitationAudit,
        evidence_scores: Sequence[EvidenceScore],
    ) -> ReflectionDecision:
        """Approve valid reports or explain why another pass is required."""

        evidence_count = len(evidence_scores)
        average_score = (
            sum(score.overall for score in evidence_scores) / evidence_count
            if evidence_count
            else 0.0
        )
        reasons: list[str] = []

        if evidence_count < self._minimum_evidence_count:
            reasons.append(
                f"At least {self._minimum_evidence_count} evidence sources are required."
            )

        if average_score < self._minimum_average_score:
            reasons.append(f"Average evidence quality is below {self._minimum_average_score:.2f}.")

        if citation_audit.unknown_source_ids:
            reasons.append("The report contains unknown source citations.")

        if citation_audit.uncited_claims:
            reasons.append("The report contains factual paragraphs without citations.")

        if not citation_audit.cited_source_ids:
            reasons.append("The report contains no recognized citations.")

        return ReflectionDecision(
            status="revise" if reasons else "approved",
            reasons=reasons,
            evidence_count=evidence_count,
            average_evidence_score=round(average_score, 4),
        )
