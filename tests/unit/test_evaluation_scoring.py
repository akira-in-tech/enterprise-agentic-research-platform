from datetime import UTC, datetime

from app.schemas.evaluation import EvaluationCase, EvaluationCaseOutcome
from app.services.evaluation import (
    build_report,
    count_matched_sections,
    extract_report_sections,
    score_case,
)


def create_case(
    *,
    expected_route: str = "deep_research",
    min_independent_sources: int = 2,
    requires_private_knowledge: bool = False,
    expected_report_sections: list[str] | None = None,
) -> EvaluationCase:
    return EvaluationCase(
        id="case-1",
        query="Compare HTTP/2 and HTTP/3.",
        expected_route=expected_route,  # type: ignore[arg-type]
        min_independent_sources=min_independent_sources,
        requires_private_knowledge=requires_private_knowledge,
        expected_report_sections=expected_report_sections or [],
    )


def create_outcome(
    *,
    status: str = "completed",
    route: str | None = "deep_research",
    cited_source_count: int = 2,
    cited_private_source_count: int = 0,
    report_sections: list[str] | None = None,
    human_review_required: bool = False,
    latency_seconds: float = 1.5,
    error: str | None = None,
) -> EvaluationCaseOutcome:
    return EvaluationCaseOutcome(
        status=status,
        route=route,  # type: ignore[arg-type]
        cited_source_count=cited_source_count,
        cited_private_source_count=cited_private_source_count,
        report_sections=report_sections or [],
        human_review_required=human_review_required,
        latency_seconds=latency_seconds,
        error=error,
    )


class TestExtractReportSections:
    def test_extracts_headings_in_document_order(self) -> None:
        markdown = (
            "# Executive Summary\n\nSome text.\n\n"
            "## Trade-offs\n\nMore text.\n\n"
            "### References\n"
        )

        assert extract_report_sections(markdown) == [
            "Executive Summary",
            "Trade-offs",
            "References",
        ]

    def test_returns_empty_list_for_no_headings(self) -> None:
        assert extract_report_sections("Just prose, no headings.") == []


class TestCountMatchedSections:
    def test_matches_case_insensitively_and_by_substring(self) -> None:
        matched = count_matched_sections(
            ["Executive Summary", "Trade-offs", "References"],
            ["executive summary", "Key Trade-offs and Risks", "See Also"],
        )

        assert matched == 2

    def test_returns_zero_for_no_expected_sections(self) -> None:
        assert count_matched_sections([], ["Executive Summary"]) == 0


class TestScoreCase:
    def test_passes_when_every_check_is_satisfied(self) -> None:
        case = create_case(expected_report_sections=["Trade-offs"])
        outcome = create_outcome(report_sections=["Key Trade-offs"])

        result = score_case(case, outcome)

        assert result.route_correct is True
        assert result.source_count_met is True
        assert result.private_knowledge_correct is True
        assert result.matched_report_sections == 1
        assert result.passed is True

    def test_fails_on_wrong_route(self) -> None:
        case = create_case(expected_route="direct")
        outcome = create_outcome(route="deep_research")

        result = score_case(case, outcome)

        assert result.route_correct is False
        assert result.passed is False

    def test_fails_when_source_minimum_is_not_met(self) -> None:
        case = create_case(min_independent_sources=3)
        outcome = create_outcome(cited_source_count=1)

        result = score_case(case, outcome)

        assert result.source_count_met is False
        assert result.passed is False

    def test_fails_when_private_knowledge_is_required_but_absent(self) -> None:
        case = create_case(requires_private_knowledge=True)
        outcome = create_outcome(cited_private_source_count=0)

        result = score_case(case, outcome)

        assert result.private_knowledge_correct is False
        assert result.passed is False

    def test_private_knowledge_not_required_always_passes_that_check(self) -> None:
        case = create_case(requires_private_knowledge=False)
        outcome = create_outcome(cited_private_source_count=0)

        result = score_case(case, outcome)

        assert result.private_knowledge_correct is True

    def test_fails_when_the_outcome_carries_an_error(self) -> None:
        case = create_case()
        outcome = create_outcome(status="failed", error="ResearchApiError: boom")

        result = score_case(case, outcome)

        assert result.passed is False

    def test_direct_route_case_with_no_expected_sections_does_not_require_a_report(
        self,
    ) -> None:
        case = create_case(
            expected_route="direct",
            min_independent_sources=0,
            expected_report_sections=[],
        )
        outcome = create_outcome(route="direct", cited_source_count=0, report_sections=[])

        result = score_case(case, outcome)

        assert result.passed is True


class TestBuildReport:
    def test_aggregates_rates_across_cases(self) -> None:
        passing_case = create_case()
        failing_case = create_case(expected_route="direct")
        results = [
            score_case(passing_case, create_outcome()),
            score_case(failing_case, create_outcome(route="deep_research")),
        ]

        report = build_report(
            run_at=datetime.now(UTC),
            commit_sha="abc1234",
            base_url="http://127.0.0.1:8000",
            llm_provider="qwen",
            cases_file="demo_profiles/engineering/evaluation_cases.jsonl",
            case_results=results,
        )

        assert report.routing_accuracy == 0.5
        assert report.completion_rate == 1.0
        assert report.overall_pass_rate == 0.5

    def test_private_knowledge_accuracy_ignores_cases_that_do_not_require_it(self) -> None:
        results = [score_case(create_case(requires_private_knowledge=False), create_outcome())]

        report = build_report(
            run_at=datetime.now(UTC),
            commit_sha=None,
            base_url="http://127.0.0.1:8000",
            llm_provider="qwen",
            cases_file="cases.jsonl",
            case_results=results,
        )

        # No private-knowledge cases in this run: the rate defaults to 1.0
        # (vacuously true) rather than dividing by zero.
        assert report.private_knowledge_accuracy == 1.0

    def test_average_latency_over_empty_results_is_zero(self) -> None:
        report = build_report(
            run_at=datetime.now(UTC),
            commit_sha=None,
            base_url="http://127.0.0.1:8000",
            llm_provider="qwen",
            cases_file="cases.jsonl",
            case_results=[],
        )

        assert report.average_latency_seconds == 0.0
        assert report.routing_accuracy == 1.0
