import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from app.schemas.evidence import EvidenceScore, EvidenceSource
from app.schemas.source import PrivateSource, WebSource
from app.schemas.workflow import EvidenceGap, EvidenceJudgment
from app.services.evidence import (
    EvidenceScorer,
    normalize_private_sources,
    normalize_web_sources,
)
from app.services.llm.base import LLMClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EvidenceJudgeResult:
    """Collect the normalized evidence pool, scores, and audit findings."""

    sources: list[EvidenceSource]
    scores: list[EvidenceScore]
    judgment: EvidenceJudgment


class EvidenceJudgeAgent:
    """Normalize, score, and audit evidence from all retrieval origins."""

    def __init__(
        self,
        scorer: EvidenceScorer,
        llm_client: LLMClient | None = None,
        *,
        minimum_source_count: int = 2,
    ) -> None:
        if minimum_source_count < 1:
            raise ValueError("minimum_source_count must be at least 1.")

        self._scorer = scorer
        self._llm_client = llm_client
        self._minimum_source_count = minimum_source_count

    async def judge(
        self,
        *,
        query: str,
        web_sources: Sequence[WebSource],
        private_sources: Sequence[PrivateSource],
        additional_sources: Sequence[EvidenceSource] = (),
    ) -> EvidenceJudgeResult:
        """Build one deduplicated and explainable evidence judgment."""

        sources = self._deduplicate(
            [
                *normalize_web_sources(web_sources),
                *normalize_private_sources(private_sources),
                *additional_sources,
            ]
        )
        scores = self._scorer.score(query=query, sources=sources)
        fallback = self._fallback_judgment(sources)
        judgment = fallback

        if self._llm_client is not None and sources:
            prompt = self._build_prompt(
                query=query,
                sources=sources,
                scores=scores,
            )

            try:
                candidate = await self._llm_client.generate_structured(
                    prompt,
                    EvidenceJudgment,
                    max_tokens=2_500,
                )
                self._validate_source_references(candidate, sources)
                judgment = candidate
            except (ValidationError, ValueError, RuntimeError):
                logger.warning(
                    "Evidence Judge structured audit failed; using deterministic fallback.",
                    exc_info=True,
                )

        return EvidenceJudgeResult(
            sources=sources,
            scores=scores,
            judgment=judgment,
        )

    def _fallback_judgment(
        self,
        sources: Sequence[EvidenceSource],
    ) -> EvidenceJudgment:
        if len(sources) >= self._minimum_source_count:
            return EvidenceJudgment()

        return EvidenceJudgment(
            gaps=[
                EvidenceGap(
                    topic="Independent source coverage",
                    reason=(
                        f"Only {len(sources)} usable source(s) were retrieved; "
                        f"at least {self._minimum_source_count} are required."
                    ),
                    source_preference="hybrid",
                )
            ]
        )

    @staticmethod
    def _deduplicate(sources: Sequence[EvidenceSource]) -> list[EvidenceSource]:
        return list({source.source_id: source for source in sources}.values())

    @staticmethod
    def _validate_source_references(
        judgment: EvidenceJudgment,
        sources: Sequence[EvidenceSource],
    ) -> None:
        known_source_ids = {source.source_id for source in sources}
        referenced_source_ids = {
            source_id for conflict in judgment.conflicts for source_id in conflict.source_ids
        }
        unknown_source_ids = referenced_source_ids - known_source_ids

        if unknown_source_ids:
            raise ValueError(
                f"Evidence Judge referenced unknown source IDs: {sorted(unknown_source_ids)}"
            )

    @staticmethod
    def _build_prompt(
        *,
        query: str,
        sources: Sequence[EvidenceSource],
        scores: Sequence[EvidenceScore],
    ) -> str:
        score_by_id = {score.source_id: score.model_dump() for score in scores}
        evidence = [
            {
                **source.model_dump(),
                "quality": score_by_id[source.source_id],
            }
            for source in sources
        ]

        return (
            "You are the Evidence Judge in an enterprise research workflow. "
            "Identify material evidence gaps and direct contradictions. Use only "
            "the supplied source IDs. Do not invent sources. When multiple sources "
            "support the same claim, prefer peer-reviewed or academic sources "
            "(source_type \"paper\") as the stronger citation, but never treat a "
            "source as a gap or contradiction just because it isn't a paper if it "
            "is clearly the most relevant evidence available.\n\n"
            f"Research question: {query}\n"
            f"Evidence: {json.dumps(evidence, ensure_ascii=False)}"
        )
