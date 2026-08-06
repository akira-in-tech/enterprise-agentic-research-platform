import re
from collections.abc import Sequence
from datetime import datetime

from app.schemas.evaluation import (
    EvaluationCase,
    EvaluationCaseOutcome,
    EvaluationCaseResult,
    EvaluationReport,
)

_HEADING_PATTERN = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)


def extract_report_sections(markdown: str) -> list[str]:
    """Return every Markdown heading's text, in document order."""

    return [match.group(1).strip() for match in _HEADING_PATTERN.finditer(markdown)]


def _section_matches(expected: str, actual_heading: str) -> bool:
    normalized_expected = expected.strip().casefold()
    normalized_actual = actual_heading.strip().casefold()

    return normalized_expected in normalized_actual or normalized_actual in normalized_expected


def count_matched_sections(
    expected_sections: Sequence[str],
    actual_headings: Sequence[str],
) -> int:
    """Count expected sections with at least one case-insensitive substring match.

    Matching is intentionally loose (substring, either direction) since an
    LLM-written report will not reproduce section titles verbatim -- this
    checks structural intent ("is there something like a Trade-offs
    section?"), not exact wording.
    """

    return sum(
        1
        for expected in expected_sections
        if any(_section_matches(expected, heading) for heading in actual_headings)
    )


def score_case(
    case: EvaluationCase,
    outcome: EvaluationCaseOutcome,
) -> EvaluationCaseResult:
    """Score one case's actual outcome against its declared expectations."""

    matched_sections = count_matched_sections(
        case.expected_report_sections,
        outcome.report_sections,
    )

    return EvaluationCaseResult(
        case=case,
        outcome=outcome,
        route_correct=(outcome.route == case.expected_route),
        source_count_met=(outcome.cited_source_count >= case.min_independent_sources),
        private_knowledge_correct=(
            outcome.cited_private_source_count > 0
            if case.requires_private_knowledge
            else True
        ),
        matched_report_sections=matched_sections,
        expected_report_sections=len(case.expected_report_sections),
    )


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0

    return numerator / denominator


def build_report(
    *,
    run_at: datetime,
    commit_sha: str | None,
    base_url: str,
    llm_provider: str,
    cases_file: str,
    case_results: Sequence[EvaluationCaseResult],
) -> EvaluationReport:
    """Aggregate scored case results into reproducible summary metrics."""

    total = len(case_results)
    private_knowledge_cases = [
        result for result in case_results if result.case.requires_private_knowledge
    ]
    section_cases = [result for result in case_results if result.expected_report_sections > 0]

    return EvaluationReport(
        run_at=run_at,
        commit_sha=commit_sha,
        base_url=base_url,
        llm_provider=llm_provider,
        cases_file=cases_file,
        case_results=list(case_results),
        routing_accuracy=_rate(
            sum(1 for result in case_results if result.route_correct),
            total,
        ),
        completion_rate=_rate(
            sum(1 for result in case_results if result.outcome.error is None),
            total,
        ),
        source_coverage_rate=_rate(
            sum(1 for result in case_results if result.source_count_met),
            total,
        ),
        private_knowledge_accuracy=_rate(
            sum(1 for result in private_knowledge_cases if result.private_knowledge_correct),
            len(private_knowledge_cases),
        ),
        report_section_coverage_rate=_rate(
            sum(result.matched_report_sections for result in section_cases),
            sum(result.expected_report_sections for result in section_cases),
        ),
        human_review_trigger_rate=_rate(
            sum(1 for result in case_results if result.outcome.human_review_required),
            total,
        ),
        average_latency_seconds=(
            sum(result.outcome.latency_seconds for result in case_results) / total if total else 0.0
        ),
        overall_pass_rate=_rate(
            sum(1 for result in case_results if result.passed),
            total,
        ),
    )
