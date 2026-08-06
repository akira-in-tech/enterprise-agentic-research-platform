import time
from collections.abc import Sequence

import httpx

from app.schemas.evaluation import EvaluationCase, EvaluationCaseOutcome, EvaluationCaseResult
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

        cited_source_count = 0
        cited_private_source_count = 0

        sources_response = await client.get(f"/research-runs/{research_run_id}/sources")

        if sources_response.status_code == httpx.codes.OK:
            for source in sources_response.json():
                if not source.get("cited"):
                    continue

                cited_source_count += 1

                if source.get("origin") == "private":
                    cited_private_source_count += 1

        answer = body.get("answer") or ""

        return EvaluationCaseOutcome(
            status=body["status"],
            route=body.get("route"),
            answer=answer,
            citation_valid=body.get("citation_valid"),
            citation_coverage=body.get("citation_coverage"),
            human_review_required=body.get("human_review_required", False),
            cited_source_count=cited_source_count,
            cited_private_source_count=cited_private_source_count,
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
) -> list[EvaluationCaseResult]:
    """Execute and score every case in order, isolating one case's failure."""

    results: list[EvaluationCaseResult] = []

    for case in cases:
        outcome = await execute_case(client, case, provider=provider)
        results.append(score_case(case, outcome))

    return results
