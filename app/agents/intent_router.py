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


# High-risk domains where the charter requires the platform to show evidence
# and uncertainty rather than an unqualified final decision, and to request
# human review instead of acting as the sole decision-maker. This is a
# narrower, more specific signal than DEEP_RESEARCH_SIGNAL_KEYWORDS' general
# "security"/"risk"/"safety" terms.
HIGH_RISK_DOMAIN_KEYWORDS = (
    # medical or health
    "medical",
    "diagnosis",
    "diagnose",
    "treatment",
    "medication",
    "dosage",
    "symptom",
    "prescri",
    # legal
    "legal advice",
    "lawsuit",
    "sue ",
    "liability",
    "regulatory compliance",
    "is it legal",
    # financial
    "financial advice",
    "investment advice",
    "should i invest",
    "tax advice",
    # safety- or security-critical
    "life-safety",
    "life safety",
    "safety-critical",
    "vulnerability",
    "exploit",
    "security incident",
)


def detect_high_risk_domain(query: str) -> bool:
    """Flag requests in medical, legal, financial, or safety-critical domains."""

    normalized_query = query.strip().lower()

    return any(keyword in normalized_query for keyword in HIGH_RISK_DOMAIN_KEYWORDS)


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
        fallback_high_risk = detect_high_risk_domain(normalized_query)

        prompt = (
            "Classify the following research request into exactly one route "
            "and flag whether it is high-risk. The request may come from any "
            "domain: engineering, cloud infrastructure, market or "
            "competitive research, product or vendor comparison, academic or "
            "technical literature, policy or regulatory research, internal "
            "company knowledge, or operations and security analysis.\n\n"
            "Use 'direct' when it can be answered briefly from stable general "
            "knowledge without collecting current sources.\n"
            "Use 'deep_research' when it requires current or time-sensitive "
            "information, multiple independent sources, comparison or "
            "trade-off analysis, private organizational knowledge, a "
            "high-uncertainty or high-risk domain, external tool calls, or a "
            "structured multi-section report.\n\n"
            "Set is_high_risk_domain to true only when the request asks for "
            "medical, legal, financial, or safety/security-critical guidance "
            "that a person could directly act on (for example a diagnosis, "
            "legal advice, investment advice, or a safety-critical "
            "recommendation). Such requests must never receive an "
            "unqualified final decision; they still get an answer, but one "
            "that surfaces evidence, uncertainty, and the need for human "
            "review.\n\n"
            "When you are confident enough to answer a security, safety, "
            "legal, financial, or medical question directly from general "
            "knowledge, that confidence is itself a reason to route it to "
            "deep_research instead: those are exactly the domains where an "
            "unverified confident answer is riskiest, and where showing "
            "current evidence and explicit uncertainty matters more than "
            "answering quickly. If the rule-based fallback below suggests "
            "deep_research, treat that as a strong prior and only override "
            "it to direct for requests that are unambiguously simple "
            "factual lookups with no risk or currency dimension at all.\n\n"
            f"Rule-based fallback suggestion: route={fallback_route}, "
            f"is_high_risk_domain={fallback_high_risk}\n"
            f"User request: {normalized_query}"
        )

        try:
            return await self._llm_client.generate_structured(
                prompt,
                IntentDecision,
                max_tokens=600,
            )
        except Exception:
            logger.exception("Claude intent classification failed; using rule fallback")

            return IntentDecision(
                route=fallback_route,
                reason="Claude classification failed; rule fallback was used.",
                is_high_risk_domain=fallback_high_risk,
            )
