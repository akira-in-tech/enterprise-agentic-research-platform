from collections.abc import Sequence

from app.agents.prompting import UNTRUSTED_CONTENT_NOTICE, wrap_untrusted_content
from app.schemas.evidence import EvidenceScore, EvidenceSource, ReflectionDecision
from app.schemas.planner import ResearchPlan
from app.schemas.workflow import ResearchAnalysis
from app.services.evidence import select_top_evidence
from app.services.llm.base import LLMClient

DEFAULT_MAX_EVIDENCE_SOURCES = 20


class WriterAgent:
    """Turn an approved analysis into the final source-traceable report."""

    def __init__(
        self,
        llm_client: LLMClient,
        *,
        max_evidence_sources: int = DEFAULT_MAX_EVIDENCE_SOURCES,
    ) -> None:
        self._llm_client = llm_client
        self._max_evidence_sources = max_evidence_sources

    async def write_report(
        self,
        *,
        query: str,
        plan: ResearchPlan,
        analysis: ResearchAnalysis,
        sources: Sequence[EvidenceSource],
        scores: Sequence[EvidenceScore],
        previous_report: str | None = None,
        revision_feedback: ReflectionDecision | None = None,
    ) -> str:
        """Generate one final report constrained to approved findings and evidence."""

        top_sources = select_top_evidence(sources, scores, limit=self._max_evidence_sources)
        score_by_source = {score.source_id: score for score in scores}
        evidence_blocks = []

        for source in top_sources:
            score = score_by_source.get(source.source_id)
            overall = score.overall if score is not None else 0.0
            evidence_blocks.append(
                "\n".join(
                    [
                        f"SOURCE_ID: {source.source_id}",
                        f"TITLE: {source.title}",
                        f"LOCATOR: {source.locator}",
                        f"ORIGIN: {source.origin}",
                        f"SOURCE_TYPE: {source.source_type}",
                        f"AUTHORS: {', '.join(source.authors) or 'unknown'}",
                        f"YEAR: {source.year if source.year is not None else 'unknown'}",
                        f"VENUE: {source.venue or 'unknown'}",
                        f"QUALITY_SCORE: {overall:.4f}",
                        f"CONTENT: {wrap_untrusted_content(source.content[:4_000])}",
                    ]
                )
            )

        outline = "\n".join(
            f"- {section.title}: {section.purpose}" for section in plan.report_outline
        )
        findings = "\n".join(
            f"- {finding.claim} ({finding.confidence}): {', '.join(finding.source_ids)}"
            for finding in analysis.findings
        )
        evidence = "\n\n".join(evidence_blocks) or "NO VERIFIED EVIDENCE"
        revision_context = ""

        if previous_report is not None and revision_feedback is not None:
            reasons = (
                "\n".join(f"- {reason}" for reason in revision_feedback.reasons)
                or "- Improve the report against the citation quality gate."
            )
            revision_context = (
                "\n\nThis is a bounded Writer revision. Address every review reason "
                "without weakening citation discipline.\n"
                f"Review reasons:\n{reasons}\n\n"
                f"Previous report:\n{previous_report}"
            )

        prompt = (
            "You are the Writer in an evidence-backed research system.\n"
            f"{UNTRUSTED_CONTENT_NOTICE}\n\n"
            f"Research question: {query}\n\n"
            f"Approved analysis: {analysis.summary}\n"
            f"Approved findings:\n{findings or 'NO APPROVED FINDINGS'}\n\n"
            f"Required outline:\n{outline}\n\n"
            f"Evidence:\n{evidence}\n\n"
            "Write the report as one Markdown ## heading per item in the required "
            "outline above, in the same order, using each item's title as the "
            "heading text. Do not merge outline items into a single section and do "
            "not invent different headings; if evidence for one outline item is "
            "thin, keep its heading and say so explicitly under it rather than "
            "dropping it. Every factual paragraph based on evidence "
            "must end with one or more exact citations such as [WEB-0123456789ABCDEF]. "
            "Use only SOURCE_ID values shown above. If evidence is insufficient, say so "
            "explicitly and do not invent facts, sources, URLs, or citations. If the research "
            "question refers to 'our', 'the organization's', 'internal', or similar "
            "possessive language, that is a request for the organization's own knowledge: "
            "look for evidence with ORIGIN 'private' first and center the report on what "
            "that source actually says, rather than substituting generic external best-"
            "practice content from ORIGIN 'web' sources that only superficially match the "
            "topic. When several sources could support the same claim, cite the one(s) with "
            "the highest QUALITY_SCORE rather than a lower-scored source that happens to "
            "appear earlier in the evidence list; independently, prefer citing sources with "
            "SOURCE_TYPE 'paper' as the stronger evidence when scores are close, but "
            "do not skip a clearly more relevant non-paper source just to cite a less "
            "relevant paper."
            f"{revision_context}"
        )
        report = (
            await self._llm_client.generate_text(
                prompt,
                max_tokens=4_500,
            )
        ).strip()

        if not report:
            raise RuntimeError("LLM provider returned an empty Writer report.")

        return report
