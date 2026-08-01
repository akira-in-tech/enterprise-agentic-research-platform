from collections.abc import Sequence

from app.schemas.evidence import EvidenceScore, EvidenceSource, ReflectionDecision
from app.schemas.planner import ResearchPlan
from app.services.llm.base import LLMClient


class AnalystAgent:
    """Generate an evidence-backed report with canonical source citations."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

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
        """Generate one report constrained to the supplied evidence."""

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
                        f"QUALITY_SCORE: {overall:.4f}",
                        f"CONTENT: {source.content[:4_000]}",
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
            f"Research question: {query}\n\n"
            f"Required outline:\n{outline}\n\n"
            f"Evidence:\n{evidence}\n\n"
            "Write a concise Markdown report. Every factual paragraph based on evidence "
            "must end with one or more exact citations such as [WEB-0123456789ABCDEF]. "
            "Use only SOURCE_ID values shown above. If evidence is insufficient, say so "
            "explicitly and do not invent facts, sources, URLs, or citations."
            f"{revision_context}"
        )
        report = (
            await self._llm_client.generate_text(
                prompt,
                max_tokens=1_500,
            )
        ).strip()

        if not report:
            raise RuntimeError("LLM provider returned an empty analyst report.")

        return report
