#!/usr/bin/env python
"""Run an evaluation_cases.jsonl file against a live, running API instance.

This is a developer/ops tool, not part of the served application: it makes
real HTTP requests (and, depending on --provider, real paid-provider calls)
against whatever --base-url points at. It is never invoked automatically by
this repository's tests or CI.

Example:
    uvicorn app.main:app &
    python scripts/run_evaluation.py \\
        --cases-file demo_profiles/engineering/evaluation_cases.jsonl \\
        --email eval@example.com --password correct-horse-battery
"""

import argparse
import asyncio
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx

from app.schemas.evaluation import EvaluationProviderPricing, EvaluationReport
from app.services.evaluation import (
    authenticate,
    build_report,
    load_evaluation_cases,
    run_evaluation,
)


def _current_commit_sha() -> str | None:
    """Return the current git commit SHA, or None outside a git checkout."""

    try:
        result = subprocess.run(  # noqa: S603
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None

    return result.stdout.strip()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases-file",
        type=Path,
        required=True,
        help="Path to an evaluation_cases.jsonl file.",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL of a running API instance (default: %(default)s).",
    )
    parser.add_argument(
        "--provider",
        choices=["claude", "qwen"],
        default="qwen",
        help="User-facing LLM provider to evaluate (default: %(default)s).",
    )
    parser.add_argument(
        "--email",
        required=True,
        help="Evaluation account email. Reused across runs via login; "
        "registered automatically on first use.",
    )
    parser.add_argument(
        "--password",
        required=True,
        help="Evaluation account password.",
    )
    parser.add_argument(
        "--tenant-name",
        default="Evaluation",
        help="Tenant name used only if the account does not exist yet (default: %(default)s).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Where to write the JSON report (default: eval_runs/eval-<timestamp>.json).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Per-request HTTP timeout in seconds (default: %(default)s).",
    )
    parser.add_argument(
        "--input-price-per-million-usd",
        type=Decimal,
        default=None,
        help="Provider input-token price used for this run. Must be paired "
        "with --output-price-per-million-usd.",
    )
    parser.add_argument(
        "--output-price-per-million-usd",
        type=Decimal,
        default=None,
        help="Provider output-token price used for this run. Must be paired "
        "with --input-price-per-million-usd.",
    )

    args = parser.parse_args(argv)

    if (args.input_price_per_million_usd is None) != (args.output_price_per_million_usd is None):
        parser.error("Both provider price arguments must be supplied together.")

    if (args.input_price_per_million_usd is not None and args.input_price_per_million_usd < 0) or (
        args.output_price_per_million_usd is not None and args.output_price_per_million_usd < 0
    ):
        parser.error("Provider prices must be non-negative.")

    return args


def _print_summary(
    report: EvaluationReport,
    output_path: Path,
) -> None:
    print(f"Evaluation report written to {output_path}")
    print(f"  commit:                     {report.commit_sha or 'unknown'}")
    print(f"  provider:                   {report.llm_provider}")
    print(f"  cases:                      {len(report.case_results)}")
    print(f"  routing accuracy:           {report.routing_accuracy:.0%}")
    print(f"  completion rate:            {report.completion_rate:.0%}")
    print(f"  source coverage rate:       {report.source_coverage_rate:.0%}")
    print(f"  private-knowledge accuracy: {report.private_knowledge_accuracy:.0%}")
    print(f"  report-section coverage:    {report.report_section_coverage_rate:.0%}")
    print(f"  human-review trigger rate:  {report.human_review_trigger_rate:.0%}")
    print(
        "  citation precision:         "
        + (f"{report.citation_precision:.0%}" if report.citation_precision is not None else "n/a")
    )
    print(
        "  unsupported-claim rate:     "
        + (
            f"{report.unsupported_claim_rate:.0%}"
            if report.unsupported_claim_rate is not None
            else "n/a"
        )
    )
    print(
        "  source diversity:           "
        + (
            f"{report.source_diversity_score:.0%}"
            if report.source_diversity_score is not None
            else "n/a"
        )
    )
    print(f"  provider input tokens:      {report.total_input_tokens}")
    print(f"  provider output tokens:     {report.total_output_tokens}")
    print(
        "  total provider cost (USD):  "
        + (
            f"${report.total_provider_cost_usd:.6f}"
            if report.total_provider_cost_usd is not None
            else "n/a (prices not supplied)"
        )
    )
    print(f"  average latency (s):        {report.average_latency_seconds:.2f}")
    print(f"  overall pass rate:          {report.overall_pass_rate:.0%}")
    print()

    for result in report.case_results:
        status = "PASS" if result.passed else "FAIL"
        print(f"  [{status}] {result.case.id}: {result.case.query[:60]}")

        if result.outcome.error:
            print(f"         error: {result.outcome.error}")


async def _run(args: argparse.Namespace) -> int:
    cases = load_evaluation_cases(args.cases_file)
    provider_pricing = (
        EvaluationProviderPricing(
            input_per_million_tokens_usd=args.input_price_per_million_usd,
            output_per_million_tokens_usd=args.output_price_per_million_usd,
        )
        if args.input_price_per_million_usd is not None
        else None
    )

    if not cases:
        print(f"No cases found in {args.cases_file}.", file=sys.stderr)
        return 1

    async with httpx.AsyncClient(base_url=args.base_url, timeout=args.timeout) as client:
        await authenticate(
            client,
            email=args.email,
            password=args.password,
            tenant_name=args.tenant_name,
        )
        case_results = await run_evaluation(
            cases,
            client,
            provider=args.provider,
            provider_pricing=provider_pricing,
        )

    report = build_report(
        run_at=datetime.now(UTC),
        commit_sha=_current_commit_sha(),
        base_url=args.base_url,
        llm_provider=args.provider,
        cases_file=str(args.cases_file),
        case_results=case_results,
        provider_pricing=provider_pricing,
    )

    output_path = args.output or Path("eval_runs") / f"eval-{report.run_at:%Y%m%dT%H%M%SZ}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    _print_summary(report, output_path)

    return 0 if report.overall_pass_rate == 1.0 else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
