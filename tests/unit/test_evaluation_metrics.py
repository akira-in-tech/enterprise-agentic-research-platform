from decimal import Decimal

from app.schemas.evaluation import EvaluationProviderPricing
from app.services.evaluation import (
    calculate_citation_precision,
    calculate_source_diversity,
    create_source_family,
    estimate_provider_cost,
    extract_citation_ids,
)


def test_extract_citation_ids_deduplicates_canonical_ids() -> None:
    answer = (
        "Supported [WEB-0123456789ABCDEF]. "
        "Repeated [WEB-0123456789ABCDEF]. "
        "Private [PRIVATE-FEDCBA9876543210]."
    )

    assert extract_citation_ids(answer) == {
        "WEB-0123456789ABCDEF",
        "PRIVATE-FEDCBA9876543210",
    }


def test_citation_precision_counts_only_resolvable_ids() -> None:
    precision = calculate_citation_precision(
        answer="Known [WEB-0123456789ABCDEF]. Unknown [WEB-AAAAAAAAAAAAAAAA].",
        known_source_ids={"WEB-0123456789ABCDEF"},
    )

    assert precision == 0.5


def test_citation_precision_is_zero_without_citations() -> None:
    assert calculate_citation_precision(answer="No evidence IDs.", known_source_ids=set()) == 0.0


def test_web_source_family_uses_normalized_hostname() -> None:
    assert (
        create_source_family(
            {
                "origin": "web",
                "locator": "https://www.example.com/research/a",
                "provider": "tavily",
            }
        )
        == "web:example.com"
    )


def test_source_diversity_groups_pages_from_the_same_domain() -> None:
    family_count, diversity = calculate_source_diversity(
        [
            {"origin": "web", "locator": "https://example.com/a"},
            {"origin": "web", "locator": "https://www.example.com/b"},
            {"origin": "web", "locator": "https://other.example/c"},
            {"origin": "private", "locator": "runbook.pdf"},
        ]
    )

    assert family_count == 3
    assert diversity == 0.75


def test_provider_cost_requires_explicit_pricing() -> None:
    assert estimate_provider_cost(input_tokens=100, output_tokens=50, pricing=None) is None


def test_provider_cost_uses_decimal_rates() -> None:
    cost = estimate_provider_cost(
        input_tokens=1_000_000,
        output_tokens=500_000,
        pricing=EvaluationProviderPricing(
            input_per_million_tokens_usd=Decimal("3"),
            output_per_million_tokens_usd=Decimal("15"),
        ),
    )

    assert cost == Decimal("10.5")
