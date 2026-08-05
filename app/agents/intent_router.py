import logging

from app.schemas.intent import IntentDecision, ResearchRoute
from app.services.llm.base import LLMClient

logger = logging.getLogger(__name__)

# Domain-neutral fallback signals. Each group maps to one of the routing
# signals in the platform charter (recency, multi-source comparison,
# regulatory/market research, private knowledge, or a high-risk domain) and
# intentionally avoids any single domain's vocabulary (e.g. no engineering-
# specific technology names) so the same rule applies to engineering,
# market, policy, or internal-knowledge questions alike.
DEEP_RESEARCH_SIGNAL_KEYWORDS = (
    # requires current or time-sensitive information
    "latest",
    "current",
    "recent",
    "up to date",
    "this year",
    # comparison, trade-off, or recommendation across options
    "compare",
    "versus",
    " vs ",
    "trade-off",
    "pros and cons",
    "which is better",
    "recommend",
    # requires evaluating multiple sources or a structured analysis
    "analyze",
    "evaluate",
    "assess",
    "landscape",
    "benchmark",
    # regulatory, policy, or compliance research
    "regulatory",
    "regulation",
    "policy",
    "compliance",
    # market or competitive research
    "market",
    "competitor",
    "competitive",
    "vendor",
    # private or internal enterprise knowledge
    "internal",
    "our company",
    "our organization",
    # high-uncertainty or high-risk domains that warrant evidence and caution
    "security",
    "risk",
    "safety",
)


def classify_route_by_rule(query: str) -> ResearchRoute:
    """Classify a query with a deterministic, domain-neutral fallback rule."""

    normalized_query = query.strip().lower()

    if any(keyword in normalized_query for keyword in DEEP_RESEARCH_SIGNAL_KEYWORDS):
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
            "Classify the following research request into exactly one route. "
            "The request may come from any domain: engineering, cloud "
            "infrastructure, market or competitive research, product or "
            "vendor comparison, academic or technical literature, policy or "
            "regulatory research, internal company knowledge, or operations "
            "and security analysis.\n\n"
            "Use 'direct' when it can be answered briefly from stable general "
            "knowledge without collecting current sources.\n"
            "Use 'deep_research' when it requires current or time-sensitive "
            "information, multiple independent sources, comparison or "
            "trade-off analysis, private organizational knowledge, a "
            "high-uncertainty or high-risk domain, external tool calls, or a "
            "structured multi-section report.\n\n"
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
            logger.exception("Claude intent classification failed; using rule fallback")

            return IntentDecision(
                route=fallback_route,
                reason="Claude classification failed; rule fallback was used.",
            )
