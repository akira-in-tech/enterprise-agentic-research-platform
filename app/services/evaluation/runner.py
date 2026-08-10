import time
from collections.abc import Mapping, Sequence
from typing import cast

import httpx

from app.schemas.evaluation import (
    EvaluationCase,
    EvaluationCaseOutcome,
    EvaluationCaseResult,
    EvaluationProviderPricing,
)
from app.services.evaluation.metrics import (
    calculate_citation_precision,
    calculate_source_diversity,
    create_source_family,
    estimate_provider_cost,
)
from app.services.evaluation.scoring import extract_report_sections, score_case


class EvaluationAuthenticationError(RuntimeError):
    """Raised when neither login nor registration establishes a session."""


async def authenticate(
    client: httpx.AsyncClient,
    *,
    email: str,
    password: str,
    tenant_name: str,
) -> None:
    """Log in, registering a new tenant on first use.

    The evaluation account is meant to be reused across runs (so a
    tenant is not created every invocation): this tries login first and
    only falls back to registration when no account exists yet.
    """

    login_response = await client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )

    if login_response.status_code == httpx.codes.OK:
        return

    register_response = await client.post(
        "/auth/register",
        json={"email": email, "password": password, "tenant_name": tenant_name},
    )

    if register_response.status_code != httpx.codes.CREATED:
        raise EvaluationAuthenticationError(
            "Could not authenticate the evaluation account: "
            f"login returned {login_response.status_code}, "
            f"register returned {register_response.status_code}."
        )


async def execute_case(
    client: httpx.AsyncClient,
    case: EvaluationCase,
    *,
    provider: str,
    provider_pricing: EvaluationProviderPricing | None = None,
) -> EvaluationCaseOutcome:
    """Run one evaluation case against a live API and capture its outcome."""

    started_at = time.monotonic()

    try:
        response = await client.post(
            "/research-runs",
            json={"query": case.query, "llm_provider": provider},
        )
        latency_seconds = time.monotonic() - started_at

        if response.status_code != httpx.codes.OK:
            return EvaluationCaseOutcome(
                status="failed",
                latency_seconds=latency_seconds,
                error=f"HTTP {response.status_code}: {response.text[:500]}",
            )

        body = response.json()
        research_run_id = body["research_run_id"]

        cited_sources: list[Mapping[str, object]] = []
        known_source_ids: set[str] = set()

        sources_response = await client.get(f"/research-runs/{research_run_id}/sources")

        if sources_response.status_code == httpx.codes.OK:
            raw_sources = cast(list[dict[str, object]], sources_response.json())

            for source in raw_sources:
                source_id = source.get("source_id")
                if isinstance(source_id, str):
                    known_source_ids.add(source_id)

                if not source.get("cited"):
                    continue

                cited_sources.append(source)

        answer = body.get("answer") or ""
        independent_source_count, source_diversity = calculate_source_diversity(cited_sources)
        private_source_families = {
            create_source_family(source)
            for source in cited_sources
            if source.get("origin") == "private"
        }
        is_deep_research = body.get("route") == "deep_research"
        citation_coverage = body.get("citation_coverage")
        raw_llm_usage = body.get("llm_usage")
        llm_usage = raw_llm_usage if isinstance(raw_llm_usage, dict) else {}
        input_tokens = int(llm_usage.get("input_tokens", 0))
        output_tokens = int(llm_usage.get("output_tokens", 0))

        return EvaluationCaseOutcome(
            status=body["status"],
            route=body.get("route"),
            answer=answer,
            citation_valid=body.get("citation_valid"),
            citation_coverage=citation_coverage,
            human_review_required=body.get("human_review_required", False),
            cited_source_count=independent_source_count,
            cited_evidence_count=len(cited_sources),
            cited_private_source_count=len(private_source_families),
            citation_precision=(
                calculate_citation_precision(
                    answer=answer,
                    known_source_ids=known_source_ids,
                )
                if is_deep_research
                else None
            ),
            unsupported_claim_rate=(
                1.0 - float(citation_coverage)
                if is_deep_research and citation_coverage is not None
                else None
            ),
            source_diversity=source_diversity if is_deep_research else None,
            llm_input_tokens=input_tokens,
            llm_output_tokens=output_tokens,
            llm_request_count=int(llm_usage.get("request_count", 0)),
            provider_cost_usd=estimate_provider_cost(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                pricing=provider_pricing,
            ),
            report_sections=extract_report_sections(answer),
            latency_seconds=latency_seconds,
            cache_hit=body.get("cache_hit", False),
        )
    except httpx.HTTPError as error:
        return EvaluationCaseOutcome(
            status="failed",
            latency_seconds=time.monotonic() - started_at,
            error=f"{type(error).__name__}: {error}",
        )


async def run_evaluation(
    cases: Sequence[EvaluationCase],
    client: httpx.AsyncClient,
    *,
    provider: str,
    provider_pricing: EvaluationProviderPricing | None = None,
) -> list[EvaluationCaseResult]:
    """Execute and score every case in order, isolating one case's failure."""

    results: list[EvaluationCaseResult] = []

    for case in cases:
        outcome = await execute_case(
            client,
            case,
            provider=provider,
            provider_pricing=provider_pricing,
        )
        results.append(score_case(case, outcome))

    return results
