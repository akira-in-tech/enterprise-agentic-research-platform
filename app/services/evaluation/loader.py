import json
from collections.abc import Iterable
from pathlib import Path

from app.schemas.evaluation import EvaluationCase


def load_evaluation_cases(path: Path) -> list[EvaluationCase]:
    """Load and validate every case from one evaluation_cases.jsonl file."""

    lines = path.read_text(encoding="utf-8").splitlines()

    return list(_parse_cases(lines))


def _parse_cases(lines: Iterable[str]) -> Iterable[EvaluationCase]:
    for line_number, raw_line in enumerate(lines, start=1):
        stripped_line = raw_line.strip()

        if not stripped_line:
            continue

        try:
            payload = json.loads(stripped_line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSON on line {line_number}: {error}") from error

        yield EvaluationCase.model_validate(payload)
