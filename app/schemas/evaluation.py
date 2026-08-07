from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.intent import ResearchRoute


class EvaluationCase(BaseModel):
    """Represent one case loaded from an evaluation_cases.jsonl file."""

    id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    expected_route: ResearchRoute
    min_independent_sources: int = Field(ge=0)
    requires_private_knowledge: bool
    expected_report_sections: list[str] = Field(default_factory=list)
    notes: str | None = None


class EvaluationCaseOutcome(BaseModel):
    """Represent what actually happened when a case was executed."""

    status: str
    route: ResearchRoute | None = None
    answer: str | None = None
    citation_valid: bool | None = None
    citation_coverage: float | None = None
    human_review_required: bool = False
    cited_source_count: int = 0
    cited_private_source_count: int = 0
    report_sections: list[str] = Field(default_factory=list)
    latency_seconds: float
    cache_hit: bool = False
    error: str | None = None


class EvaluationCaseResult(BaseModel):
    """Score one case's outcome against its expectations."""

    case: EvaluationCase
    outcome: EvaluationCaseOutcome
    route_correct: bool
    source_count_met: bool
    private_knowledge_correct: bool
    matched_report_sections: int
    expected_report_sections: int

    @property
    def passed(self) -> bool:
        """Return whether every individual check for this case passed.

        Report-section coverage is deliberately excluded from this gate.
        Five published evaluation runs across two different models (a
        local 8B model and Claude) showed the same pattern: reports with
        sound, correctly-cited, multi-section structure were vetoed
        outright because their section titles didn't case-insensitive
        substring-match the fixture's exact wording (e.g. "Key Features
        of HTTP/3" vs. the fixture's "Technical Background"). That is a
        scoring-method blind spot, not a signal that the case actually
        failed -- see docs/evaluation.md's "Fifth run" section for the
        evidence. report_section_coverage_rate is still computed and
        reported for anyone auditing structure quality directly; it just
        no longer single-handedly fails an otherwise-correct case.
        """

        if self.outcome.error is not None:
            return False

        return self.route_correct and self.source_count_met and self.private_knowledge_correct


class EvaluationReport(BaseModel):
    """Aggregate a full evaluation run into reproducible summary metrics."""

    run_at: datetime
    commit_sha: str | None = None
    base_url: str
    llm_provider: str
    cases_file: str
    case_results: list[EvaluationCaseResult]

    routing_accuracy: float
    completion_rate: float
    source_coverage_rate: float
    private_knowledge_accuracy: float
    report_section_coverage_rate: float
    human_review_trigger_rate: float
    average_latency_seconds: float
    overall_pass_rate: float
