from collections.abc import Callable
from uuid import uuid4

import pytest

from app.agents.local_scout import LocalScoutAgent
from app.schemas.planner import ReportSection, ResearchPlan, ResearchTask
from app.schemas.source import PrivateSource


def create_plan() -> ResearchPlan:
    return ResearchPlan(
        goal="Evaluate queue delivery guarantees.",
        sub_questions=[
            "What delivery guarantee is implemented?",
            "How are worker failures recovered?",
        ],
        tasks=[
            ResearchTask(
                title="Delivery guarantees",
                search_query="queue delivery guarantees",
                rationale="Identify the documented delivery model.",
            ),
            ResearchTask(
                title="Failure recovery",
                search_query="worker failure recovery",
                rationale="Find the internal recovery procedure.",
            ),
        ],
        report_outline=[
            ReportSection(title="Conclusion", purpose="State the delivery guarantee."),
            ReportSection(title="Evidence", purpose="Present the supporting evidence."),
            ReportSection(title="Risks", purpose="Explain remaining failure risks."),
        ],
    )


def create_source(
    source_id: str,
    *,
    score: float,
    content: str = "Internal queue architecture evidence.",
) -> PrivateSource:
    suffix = source_id.removeprefix("PRIVATE-")

    return PrivateSource(
        source_id=source_id,
        document_id=f"DOC-{suffix}",
        chunk_id=f"CHK-{suffix}",
        filename="queue.md",
        media_type="text/markdown",
        content=content,
        score=score,
    )


class RecordingRetriever:
    def __init__(
        self,
        response_for_query: Callable[[str], list[PrivateSource]],
        *,
        error_query: str | None = None,
    ) -> None:
        self._response_for_query = response_for_query
        self._error_query = error_query
        self.calls: list[tuple[str, str, int]] = []

    async def retrieve(
        self,
        *,
        query: str,
        tenant_id: str,
        limit: int = 5,
    ) -> list[PrivateSource]:
        self.calls.append((query, tenant_id, limit))

        if query == self._error_query:
            raise RuntimeError("private vector store unavailable")

        return self._response_for_query(query)


@pytest.mark.anyio
async def test_local_scout_uses_plan_queries_and_tenant_scope() -> None:
    tenant_id = uuid4()
    retriever = RecordingRetriever(
        lambda query: [
            create_source(
                "PRIVATE-0123456789ABCDEF"
                if query == "queue delivery guarantees"
                else "PRIVATE-FEDCBA9876543210",
                score=0.9,
            )
        ]
    )
    agent = LocalScoutAgent(
        retriever,
        max_results_per_task=4,
    )

    result = await agent.scout(create_plan(), tenant_id)

    assert len(result.sources) == 2
    assert result.errors == []
    assert retriever.calls == [
        ("queue delivery guarantees", str(tenant_id), 4),
        ("worker failure recovery", str(tenant_id), 4),
    ]


@pytest.mark.anyio
async def test_local_scout_deduplicates_sources_and_keeps_the_best_score() -> None:
    low_score = create_source("PRIVATE-0123456789ABCDEF", score=0.4)
    high_score = create_source("PRIVATE-0123456789ABCDEF", score=0.95)
    retriever = RecordingRetriever(
        lambda query: [low_score] if query == "queue delivery guarantees" else [high_score]
    )
    agent = LocalScoutAgent(retriever)

    result = await agent.scout(create_plan(), uuid4())

    assert result.sources == [high_score]


@pytest.mark.anyio
async def test_local_scout_preserves_success_when_another_query_fails() -> None:
    source = create_source("PRIVATE-0123456789ABCDEF", score=0.9)
    retriever = RecordingRetriever(
        lambda _: [source],
        error_query="worker failure recovery",
    )
    agent = LocalScoutAgent(retriever)

    result = await agent.scout(create_plan(), uuid4())

    assert result.sources == [source]
    assert result.errors == ["Failure recovery: RuntimeError: private vector store unavailable"]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"max_concurrency": 0}, "max_concurrency must be at least 1"),
        ({"max_results_per_task": 0}, "max_results_per_task must be between 1 and 20"),
        ({"max_sources": 0}, "max_sources must be at least 1"),
        ({"task_timeout_seconds": 0.0}, "task_timeout_seconds must be greater than 0"),
    ],
)
def test_local_scout_rejects_invalid_limits(
    overrides: dict[str, int | float],
    message: str,
) -> None:
    retriever = RecordingRetriever(lambda _: [])

    with pytest.raises(ValueError, match=message):
        LocalScoutAgent(retriever, **overrides)  # type: ignore[arg-type]
