import logging
from collections.abc import Sequence

from pydantic import ValidationError

from app.agents.prompting import UNTRUSTED_CONTENT_NOTICE, wrap_untrusted_content
from app.schemas.evidence import EvidenceScore, EvidenceSource, ReflectionDecision
from app.schemas.planner import ResearchPlan
from app.schemas.workflow import ResearchAnalysis
from app.services.evidence import select_top_evidence
from app.services.llm.base import LLMClient

logger = logging.getLogger(__name__)

DEFAULT_MAX_EVIDENCE_SOURCES = 20


class AnalystAgent:
    """Produce evidence-backed analysis before final report writing."""

    def __init__(
        self,
        llm_client: LLMClient,
        *,
        max_evidence_sources: int = DEFAULT_MAX_EVIDENCE_SOURCES,
    ) -> None:
        self._llm_client = llm_client
        self._max_evidence_sources = max_evidence_sources

    async def analyze(
        self,
        *,
        query: str,
        sources: Sequence[EvidenceSource],
        scores: Sequence[EvidenceScore],
    ) -> ResearchAnalysis:
        """Generate structured findings constrained to the supplied evidence."""

        top_sources = select_top_evidence(sources, scores, limit=self._max_evidence_sources)
        score_by_source = {score.source_id: score.model_dump() for score in scores}
        evidence = [
            {
                **source.model_dump(),
                "content": wrap_untrusted_content(source.content),
                "quality": score_by_source.get(source.source_id),
            }
            for source in top_sources
        ]
        prompt = (
            "You are the Analyst in an evidence-backed research workflow. "
            "Produce structured conclusions, not a final report. Every finding must "
            "reference one or more supplied source IDs. Mark needs_more_research when "
            "material questions remain unresolved. Never invent facts or source IDs. If "
            "the research question refers to 'our', 'the organization's', 'internal', or "
            "similar possessive language, that is a request for the organization's own "
            "knowledge: ground findings in evidence with origin 'private' first, rather "
            "than generic external web content that only superficially matches the "
            "topic.\n\n"
            f"{UNTRUSTED_CONTENT_NOTICE}\n\n"
            f"Research question: {query}\n"
            f"Evidence: {evidence}"
        )
        try:
            analysis = await self._llm_client.generate_structured(
                prompt,
                ResearchAnalysis,
                max_tokens=8_000,
            )
            known_source_ids = {source.source_id for source in sources}
            cited_source_ids = {
                source_id for finding in analysis.findings for source_id in finding.source_ids
            }
            unknown_source_ids = cited_source_ids - known_source_ids

            if unknown_source_ids:
                raise RuntimeError(
                    f"Analyst referenced unknown source IDs: {sorted(unknown_source_ids)}"
                )

            return analysis
        except (ValidationError, ValueError, RuntimeError):
            logger.warning(
                "Analyst structured analysis failed; falling back to an empty analysis "
                "so the Writer can still work directly from the evidence pool.",
                exc_info=True,
            )
            return ResearchAnalysis(
                summary=(
                    "Structured analysis was not available for this run; "
                    "the report below is written directly from the evidence pool."
                ),
                findings=[],
                needs_more_research=False,
                gaps=[],
            )

    async def write_report(
        self,
        *,
        query: str,
        plan: ResearchPlan,
        sources: Sequence[EvidenceSource],
        scores: Sequence[EvidenceScore],
        previous_report: str | None = None,
        revision_feedback: ReflectionDecision | None = None,
    ) -> str:
        """Generate a legacy report while callers migrate to WriterAgent."""

        score_by_source = {score.source_id: score for score in scores}
        evidence_blocks = []

        for source in sources:
            score = score_by_source.get(source.source_id)
            overall = score.overall if score is not None else 0.0
            evidence_blocks.append(
                "\n".join(
                    [
                        f"SOURCE_ID: {source.source_id}",
                        f"TITLE: {source.title}",
                        f"LOCATOR: {source.locator}",
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
        evidence = "\n\n".join(evidence_blocks) or "NO VERIFIED EVIDENCE"
        revision_context = ""

        if previous_report is not None and revision_feedback is not None:
            reasons = (
                "\n".join(f"- {reason}" for reason in revision_feedback.reasons)
                or "- Improve the report against the evidence quality gate."
            )
            revision_context = (
                "\n\nThis is a bounded revision pass. Address every review reason "
                "without weakening citation discipline.\n"
                f"Review reasons:\n{reasons}\n\n"
                f"Previous report:\n{previous_report}"
            )

        prompt = (
            "You are the analyst in an evidence-backed research system.\n"
            f"{UNTRUSTED_CONTENT_NOTICE}\n\n"
            f"Research question: {query}\n\n"
            f"Required outline:\n{outline}\n\n"
            f"Evidence:\n{evidence}\n\n"
            "Write a concise Markdown report. Every factual paragraph based on evidence "
            "must end with one or more exact citations such as [WEB-0123456789ABCDEF]. "
            "Use only SOURCE_ID values shown above. If evidence is insufficient, say so "
            "explicitly and do not invent facts, sources, URLs, or citations. When multiple "
            "sources support the same claim, prefer citing sources with SOURCE_TYPE 'paper' "
            "as the stronger evidence, but do not skip a clearly more relevant non-paper "
            "source just to cite a less relevant paper."
            f"{revision_context}"
        )
        report = (
            await self._llm_client.generate_text(
                prompt,
                max_tokens=4_000,
            )
        ).strip()

        if not report:
            raise RuntimeError("LLM provider returned an empty analyst report.")

        return report
