from collections.abc import Sequence

from app.schemas.evidence import CitationAudit, EvidenceScore, ReflectionDecision
from app.schemas.workflow import (
    EvidenceGap,
    ReflectionResult,
    ResearchAnalysis,
    SupplementaryResearchQuery,
)
from app.services.llm.base import LLMClient


class ReflectionAgent:
    """Apply a deterministic quality gate to an analyst report."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
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
        self._llm_client = llm_client

    async def reflect(
        self,
        *,
        analysis: ResearchAnalysis,
        evidence_gaps: Sequence[EvidenceGap],
        attempted_queries: Sequence[str],
    ) -> ReflectionResult:
        """Decide whether evidence gaps require one focused retrieval round."""

        gaps = [*evidence_gaps, *analysis.gaps]

        if not analysis.needs_more_research and not gaps:
            return ReflectionResult(
                status="write",
                summary="The evidence and analysis are sufficient for final writing.",
            )

        fallback = self._fallback_follow_up(
            gaps=gaps,
            attempted_queries=attempted_queries,
        )

        if self._llm_client is None:
            return fallback

        prompt = (
            "You are the Reflect agent in an enterprise research workflow. "
            "Create focused supplementary queries for unresolved evidence gaps. "
            "Do not repeat attempted queries. Return status continue_research when at "
            "least one new query is available; otherwise return status write and explain "
            "the limitation.\n\n"
            f"Analysis summary: {analysis.summary}\n"
            f"Evidence gaps: {[gap.model_dump() for gap in gaps]}\n"
            f"Attempted queries: {list(attempted_queries)}"
        )

        try:
            result = await self._llm_client.generate_structured(
                prompt,
                ReflectionResult,
                max_tokens=2_000,
            )
        except Exception:
            return fallback

        normalized_attempts = {query.strip().casefold() for query in attempted_queries}
        unique_queries: list[SupplementaryResearchQuery] = []
        seen_queries = set(normalized_attempts)

        for query in result.supplementary_queries:
            normalized_query = query.query.strip().casefold()

            if normalized_query in seen_queries:
                continue

            seen_queries.add(normalized_query)
            unique_queries.append(query)

        if not unique_queries:
            return ReflectionResult(
                status="write",
                summary=(
                    "No new supplementary query remained after duplicate removal; "
                    "write with explicit limitations."
                ),
            )

        return ReflectionResult(
            status="continue_research",
            summary=result.summary,
            supplementary_queries=unique_queries,
        )

    @staticmethod
    def _fallback_follow_up(
        *,
        gaps: Sequence[EvidenceGap],
        attempted_queries: Sequence[str],
    ) -> ReflectionResult:
        attempted = {query.strip().casefold() for query in attempted_queries}
        queries: list[SupplementaryResearchQuery] = []

        for gap in gaps:
            query = gap.topic.strip()

            if query.casefold() in attempted:
                continue

            queries.append(
                SupplementaryResearchQuery(
                    query=query,
                    source_preference=gap.source_preference,
                    reason=gap.reason,
                )
            )

        if not queries:
            return ReflectionResult(
                status="write",
                summary="No new query can fill the remaining evidence gaps.",
            )

        return ReflectionResult(
            status="continue_research",
            summary="Run focused follow-up retrieval for the unresolved evidence gaps.",
            supplementary_queries=queries[:6],
        )

    def review(
        self,
        *,
        citation_audit: CitationAudit,
        evidence_scores: Sequence[EvidenceScore],
        is_high_risk_domain: bool = False,
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

        top_score = max(evidence_scores, key=lambda score: score.overall, default=None)
        if (
            top_score is not None
            and top_score.source_id.startswith("PRIVATE-")
            and top_score.source_id not in citation_audit.cited_source_ids
        ):
            reasons.append(
                "The highest-scored source in the evidence pool is your "
                f"organization's own private knowledge ({top_score.source_id}) "
                "and it was not cited. If it directly answers the query, cite "
                "it explicitly using its exact source ID."
            )

        # A high-risk domain always requires human review, independent of
        # citation/evidence quality: sufficient evidence makes a report
        # approvable, but it never makes a medical, legal, financial, or
        # safety-critical conclusion safe to act on without a human check.
        human_review_reason = (
            (
                "This request touches a medical, legal, financial, or "
                "safety/security-critical domain. Treat this report as "
                "evidence and context, not an unqualified final decision, "
                "and route it through human review before acting on it."
            )
            if is_high_risk_domain
            else None
        )

        return ReflectionDecision(
            status="revise" if reasons else "approved",
            reasons=reasons,
            evidence_count=evidence_count,
            average_evidence_score=round(average_score, 4),
            human_review_required=is_high_risk_domain,
            human_review_reason=human_review_reason,
        )
