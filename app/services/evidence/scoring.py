import re
from collections.abc import Iterable

from app.schemas.evidence import EvidenceScore, EvidenceSource

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./+-]*")


class EvidenceScorer:
    """Score evidence with deterministic and explainable quality signals."""

    def score(
        self,
        *,
        query: str,
        sources: Iterable[EvidenceSource],
    ) -> list[EvidenceScore]:
        """Return scores in source order without provider-specific assumptions."""

        query_tokens = self._tokens(query)

        if not query_tokens:
            raise ValueError("query must contain searchable terms.")

        return [
            self._score_source(
                query_tokens=query_tokens,
                source=source,
            )
            for source in sources
        ]

    def _score_source(
        self,
        *,
        query_tokens: set[str],
        source: EvidenceSource,
    ) -> EvidenceScore:
        source_tokens = self._tokens(f"{source.title} {source.content}")
        lexical_relevance = len(query_tokens & source_tokens) / len(query_tokens)

        if source.retrieval_score is None:
            relevance = lexical_relevance
        else:
            semantic_relevance = (source.retrieval_score + 1.0) / 2.0
            relevance = max(lexical_relevance, semantic_relevance)

        content_quality = min(len(source.content.strip()) / 500.0, 1.0)
        traceability = 1.0 if source.locator.strip() else 0.0
        overall = (0.65 * relevance) + (0.25 * content_quality) + (0.10 * traceability)

        return EvidenceScore(
            source_id=source.source_id,
            relevance=round(relevance, 4),
            content_quality=round(content_quality, 4),
            traceability=round(traceability, 4),
            overall=round(overall, 4),
        )

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return {token.lower() for token in TOKEN_PATTERN.findall(value) if len(token) >= 2}
