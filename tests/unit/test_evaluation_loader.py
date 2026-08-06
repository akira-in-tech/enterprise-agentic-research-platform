from pathlib import Path

import pytest
from pydantic import ValidationError

from app.services.evaluation import load_evaluation_cases

FIXTURE_PATH = Path("demo_profiles/engineering/evaluation_cases.jsonl")


def test_loads_the_real_engineering_fixture_file() -> None:
    cases = load_evaluation_cases(FIXTURE_PATH)

    assert len(cases) == 5
    assert cases[0].id == "eval-eng-001"
    assert cases[0].expected_route == "deep_research"
    assert cases[0].min_independent_sources == 3
    assert cases[0].requires_private_knowledge is False
    assert "Executive Summary" in cases[0].expected_report_sections

    direct_case = next(case for case in cases if case.expected_route == "direct")
    assert direct_case.min_independent_sources == 0
    assert direct_case.expected_report_sections == []


def test_skips_blank_lines(tmp_path: Path) -> None:
    cases_file = tmp_path / "cases.jsonl"
    cases_file.write_text(
        '\n{"id": "a", "query": "q", "expected_route": "direct", '
        '"min_independent_sources": 0, "requires_private_knowledge": false}\n\n',
        encoding="utf-8",
    )

    cases = load_evaluation_cases(cases_file)

    assert len(cases) == 1
    assert cases[0].id == "a"


def test_rejects_invalid_json(tmp_path: Path) -> None:
    cases_file = tmp_path / "cases.jsonl"
    cases_file.write_text("not json\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid JSON on line 1"):
        load_evaluation_cases(cases_file)


def test_rejects_a_case_missing_required_fields(tmp_path: Path) -> None:
    cases_file = tmp_path / "cases.jsonl"
    cases_file.write_text('{"id": "a"}\n', encoding="utf-8")

    with pytest.raises(ValidationError):
        load_evaluation_cases(cases_file)
