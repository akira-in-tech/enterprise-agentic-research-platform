import re
from collections.abc import Mapping, Sequence
from decimal import Decimal
from urllib.parse import urlsplit

from app.schemas.evaluation import EvaluationProviderPricing

_CANONICAL_CITATION_PATTERN = re.compile(r"\[((?:WEB|PRIVATE|MCP|PAPER)-[0-9A-F]{16})\]")


def extract_citation_ids(markdown: str) -> set[str]:
    """Return unique canonical citation IDs present in an answer."""

    return set(_CANONICAL_CITATION_PATTERN.findall(markdown))


def calculate_citation_precision(
    *,
    answer: str,
    known_source_ids: set[str],
) -> float:
    """Measure how many cited IDs resolve to sources returned by the API.

    This is an integrity metric, not a semantic-entailment judgment. A report
    with no canonical citations scores zero rather than receiving vacuous
    credit.
    """

    cited_ids = extract_citation_ids(answer)

    if not cited_ids:
        return 0.0

    return len(cited_ids & known_source_ids) / len(cited_ids)


def create_source_family(source: Mapping[str, object]) -> str:
    """Build a stable independent-source family for diversity scoring."""

    origin = str(source.get("origin") or "unknown").strip().lower()
    locator = str(source.get("locator") or "").strip()
    provider = str(source.get("provider") or "unknown").strip().lower()

    if origin == "web":
        hostname = (urlsplit(locator).hostname or locator).strip().lower()
        if hostname.startswith("www."):
            hostname = hostname[4:]
        return f"web:{hostname or provider}"

    if origin == "private":
        return f"private:{locator.casefold() or provider}"

    if origin == "mcp":
        return f"mcp:{provider}"

    return f"{origin}:{locator.casefold() or provider}"


def calculate_source_diversity(
    cited_sources: Sequence[Mapping[str, object]],
) -> tuple[int, float]:
    """Return independent family count and family-to-evidence ratio."""

    if not cited_sources:
        return 0, 0.0

    families = {create_source_family(source) for source in cited_sources}
    return len(families), len(families) / len(cited_sources)


def estimate_provider_cost(
    *,
    input_tokens: int,
    output_tokens: int,
    pricing: EvaluationProviderPricing | None,
) -> Decimal | None:
    """Estimate API cost from provider usage and explicitly supplied rates."""

    if pricing is None:
        return None

    million = Decimal(1_000_000)
    return (
        Decimal(input_tokens) * pricing.input_per_million_tokens_usd
        + Decimal(output_tokens) * pricing.output_per_million_tokens_usd
    ) / million
