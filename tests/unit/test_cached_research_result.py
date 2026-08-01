import pytest
from pydantic import ValidationError

from app.schemas.cache import CachedResearchResult
from app.schemas.evidence import EvidenceScore, EvidenceSource


def test_cached_research_result_json_round_trip() -> None:
    result = CachedResearchResult(
        llm_provider="ollama",
        workflow_status="direct_answer_completed",
        route="direct",
        route_reason=("The question can be answered using stable knowledge."),
        answer=(
            "A mutex prevents multiple threads from entering a critical section simultaneously."
        ),
    )

    encoded = result.model_dump_json()
    restored = CachedResearchResult.model_validate_json(
        encoded,
    )

    assert restored == result
    assert restored.llm_provider == "ollama"
    assert restored.route == "direct"
    assert restored.answer is not None


def test_cached_research_result_preserves_durable_evidence_payload() -> None:
    source = EvidenceSource(
        source_id="WEB-0123456789ABCDEF",
        origin="web",
        title="HTTP specification",
        locator="https://example.com/http",
        content="HTTP evidence.",
        provider="fixture",
    )
    score = EvidenceScore(
        source_id=source.source_id,
        relevance=0.9,
        content_quality=0.8,
        traceability=1,
        overall=0.88,
    )
    result = CachedResearchResult(
        llm_provider="ollama",
        workflow_status="research_report_completed",
        route="deep_research",
        answer="HTTP report.",
        report="HTTP report.",
        evidence_sources=[source],
        evidence_scores=[score],
        reflection_attempts=2,
    )

    restored = CachedResearchResult.model_validate_json(result.model_dump_json())

    assert restored.report == "HTTP report."
    assert restored.evidence_sources == [source]
    assert restored.evidence_scores == [score]
    assert restored.reflection_attempts == 2


def test_cached_research_result_does_not_require_answer() -> None:
    result = CachedResearchResult(
        llm_provider="anthropic",
        workflow_status="research_completed",
        route="deep_research",
        route_reason="The request requires multi-source research.",
    )

    assert result.answer is None


def test_cached_research_result_rejects_unknown_provider() -> None:
    with pytest.raises(
        ValidationError,
    ):
        CachedResearchResult.model_validate(
            {
                "llm_provider": "openai",
                "workflow_status": "completed",
            }
        )


def test_cached_research_result_rejects_blank_status() -> None:
    with pytest.raises(
        ValidationError,
    ):
        CachedResearchResult.model_validate(
            {
                "llm_provider": "ollama",
                "workflow_status": "   ",
            }
        )


@pytest.mark.parametrize(
    "field_name",
    [
        "route_reason",
        "answer",
    ],
)
def test_cached_research_result_rejects_blank_optional_text(
    field_name: str,
) -> None:
    payload: dict[str, object] = {
        "llm_provider": "ollama",
        "workflow_status": "completed",
        field_name: "   ",
    }

    with pytest.raises(
        ValidationError,
    ):
        CachedResearchResult.model_validate(
            payload,
        )


def test_cached_research_result_rejects_unknown_fields() -> None:
    with pytest.raises(
        ValidationError,
    ):
        CachedResearchResult.model_validate(
            {
                "llm_provider": "ollama",
                "workflow_status": "completed",
                "query": "Private research query.",
            }
        )
