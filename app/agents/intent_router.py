import logging

from app.schemas.intent import IntentDecision, ResearchRoute
from app.services.llm.base import LLMClient

logger = logging.getLogger(__name__)

DEEP_RESEARCH_KEYWORDS = (
    "compare",
    "architecture",
    "trade-off",
    "distributed",
    "kubernetes",
    "docker",
    "network",
    "performance",
    "security",
    "benchmark",
    "consistency",
    "consensus",
    "latest",
    "current",
)


def classify_route_by_rule(query: str) -> ResearchRoute:
    """Classify a query with a deterministic fallback rule."""

    normalized_query = query.strip().lower()

    if any(keyword in normalized_query for keyword in DEEP_RESEARCH_KEYWORDS):
        return "deep_research"

    return "direct"


class IntentRouter:
    """Route requests using Claude with a deterministic fallback."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    async def classify(self, query: str) -> IntentDecision:
        """Classify a request as direct or deep research."""

        normalized_query = query.strip()

        if not normalized_query:
            raise ValueError("Query must not be empty.")

        fallback_route = classify_route_by_rule(normalized_query)

        prompt = (
            "Classify the following software engineering request into exactly "
            "one route.\n\n"
            "Use 'direct' when it can be answered briefly from stable technical "
            "knowledge without collecting current sources.\n"
            "Use 'deep_research' when it requires current information, multiple "
            "sources, comparison, architectural analysis, evidence, security "
            "analysis, performance analysis, or detailed trade-offs.\n\n"
            f"Rule-based fallback suggestion: {fallback_route}\n"
            f"User request: {normalized_query}"
        )

        try:
            return await self._llm_client.generate_structured(
                prompt,
                IntentDecision,
                max_tokens=200,
            )
        except Exception:
            logger.exception(
                "Claude intent classification failed; using rule fallback"
            )

            return IntentDecision(
                route=fallback_route,
                reason="Claude classification failed; rule fallback was used.",
            )