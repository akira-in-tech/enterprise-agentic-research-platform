from collections.abc import Sequence
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest

from app.agents.local_scout import LocalScoutResult
from app.schemas.intent import IntentDecision
from app.schemas.planner import (
    ReportSection,
    ResearchPlan,
    ResearchTask,
)
from app.schemas.source import PrivateSource
from app.services.search.base import SearchResult
from app.services.search.executor import ResearchTaskResult
from app.services.search.results import create_web_source_id
from app.workflow import graph as graph_module
from app.workflow.graph import build_research_graph


async def fake_direct_classifier(_: str) -> IntentDecision:
    return IntentDecision(
        route="direct",
        reason="The request uses stable technical knowledge.",
    )


async def fake_research_classifier(_: str) -> IntentDecision:
    return IntentDecision(
        route="deep_research",
        reason="The request requires current sources and comparison.",
    )


async def fake_direct_answer(query: str) -> str:
    return f"Direct answer for: {query}"


async def fake_plan_creator(_: str) -> ResearchPlan:
    return ResearchPlan(
        goal="Compare HTTP/2 and HTTP/3.",
        sub_questions=[
            "How do HTTP/2 and HTTP/3 differ architecturally?",
            "What security and reliability trade-offs do they have?",
        ],
        tasks=[
            ResearchTask(
                title="Protocol architecture",
                search_query="HTTP/2 HTTP/3 architecture differences",
                rationale="Compare the underlying protocol designs.",
            ),
            ResearchTask(
                title="Security trade-offs",
                search_query="HTTP/2 HTTP/3 security trade-offs",
                rationale="Evaluate protocol security characteristics.",
            ),
        ],
        report_outline=[
            ReportSection(
                title="Technical Background",
                purpose="Explain the foundations of both protocols.",
            ),
            ReportSection(
                title="Architecture",
                purpose="Compare their transport and connection models.",
            ),
            ReportSection(
                title="Trade-offs",
                purpose="Evaluate reliability, security, and performance.",
            ),
        ],
    )


def create_successful_outcome(
    task: ResearchTask,
    index: int,
) -> ResearchTaskResult:
    return ResearchTaskResult(
        task=task,
        results=[
            SearchResult(
                title="Shared HTTP specification",
                url="https://example.com/shared-http-source",
                content="Shared evidence relevant to both tasks.",
                source="fake",
            ),
            SearchResult(
                title=f"Technical source {index}",
                url=f"https://example.com/source-{index}",
                content=f"Evidence for {task.search_query}.",
                source="fake",
            ),
        ],
    )


async def fake_successful_search(
    plan: ResearchPlan,
) -> list[ResearchTaskResult]:
    return [
        create_successful_outcome(task, index) for index, task in enumerate(plan.tasks, start=1)
    ]


async def fake_private_scout(
    _: ResearchPlan,
    tenant_id: UUID,
    *,
    document_ids: Sequence[str] | None = None,
) -> LocalScoutResult:
    suffix = tenant_id.hex[:16].upper()

    return LocalScoutResult(
        sources=[
            PrivateSource(
                source_id=f"PRIVATE-{suffix}",
                document_id=f"DOC-{suffix}",
                chunk_id=f"CHK-{suffix}",
                filename="internal-http.md",
                media_type="text/markdown",
                content="Internal HTTP deployment evidence.",
                score=0.93,
            )
        ],
        errors=[],
    )


async def fake_partial_search(
    plan: ResearchPlan,
) -> list[ResearchTaskResult]:
    first_task, second_task = plan.tasks

    return [
        create_successful_outcome(first_task, 1),
        ResearchTaskResult(
            task=second_task,
            results=[],
            error="RuntimeError: simulated provider failure.",
        ),
    ]


async def fake_failed_search(
    plan: ResearchPlan,
) -> list[ResearchTaskResult]:
    return [
        ResearchTaskResult(
            task=task,
            results=[],
            error="RuntimeError: simulated provider failure.",
        )
        for task in plan.tasks
    ]


async def fake_empty_search(
    plan: ResearchPlan,
) -> list[ResearchTaskResult]:
    return [
        ResearchTaskResult(
            task=task,
            results=[],
        )
        for task in plan.tasks
    ]


@pytest.mark.anyio
async def test_research_graph_generates_direct_answer() -> None:
    graph = build_research_graph(
        fake_direct_classifier,
        fake_plan_creator,
        fake_direct_answer,
        fake_successful_search,
    )

    result = await graph.ainvoke(
        {
            "query": "Explain idempotency in REST APIs.",
            "status": "pending",
        }
    )

    assert result["route"] == "direct"
    assert result["status"] == "direct_answer_completed"
    assert result["answer"] == ("Direct answer for: Explain idempotency in REST APIs.")
    assert "plan" not in result
    assert "web_search_results" not in result
    assert "web_sources" not in result


@pytest.mark.anyio
async def test_research_graph_searches_for_deep_research() -> None:
    graph = build_research_graph(
        fake_research_classifier,
        fake_plan_creator,
        fake_direct_answer,
        fake_successful_search,
    )

    result = await graph.ainvoke(
        {
            "query": "Compare HTTP/2 and HTTP/3 using current sources.",
            "status": "pending",
        }
    )

    assert result["route"] == "deep_research"
    assert result["status"] == "web_search_completed"
    assert result["plan"].goal == "Compare HTTP/2 and HTTP/3."
    assert len(result["plan"].sub_questions) == 2
    assert len(result["plan"].report_outline) == 3

    outcomes = result["web_search_results"]

    assert len(outcomes) == 2
    assert all(outcome.succeeded for outcome in outcomes)
    assert "answer" not in result
    assert all(len(outcome.results) == 2 for outcome in outcomes)

    web_sources = result["web_sources"]

    assert len(web_sources) == 3
    assert [source.url for source in web_sources] == [
        "https://example.com/shared-http-source",
        "https://example.com/source-1",
        "https://example.com/source-2",
    ]

    assert [source.source_id for source in web_sources] == [
        create_web_source_id("https://example.com/shared-http-source"),
        create_web_source_id("https://example.com/source-1"),
        create_web_source_id("https://example.com/source-2"),
    ]

    assert all(source.provider == "fake" for source in web_sources)


@pytest.mark.anyio
async def test_research_graph_runs_tenant_scoped_local_scout_when_configured() -> None:
    tenant_id = uuid4()
    graph = build_research_graph(
        fake_research_classifier,
        fake_plan_creator,
        fake_direct_answer,
        fake_successful_search,
        scout_private_knowledge=fake_private_scout,
    )

    result = await graph.ainvoke(
        {
            "query": "Compare HTTP/2 and HTTP/3 using internal evidence.",
            "tenant_id": tenant_id,
        }
    )

    assert result["local_scout_errors"] == []
    assert len(result["private_sources"]) == 1
    assert result["private_sources"][0].source_id == (f"PRIVATE-{tenant_id.hex[:16].upper()}")
    assert result["status"] == "web_search_completed"


@pytest.mark.anyio
async def test_research_graph_forwards_document_ids_to_local_scout() -> None:
    tenant_id = uuid4()
    received_document_ids: list[Sequence[str] | None] = []

    async def recording_private_scout(
        _: ResearchPlan,
        scoped_tenant_id: UUID,
        *,
        document_ids: Sequence[str] | None = None,
    ) -> LocalScoutResult:
        received_document_ids.append(document_ids)

        return await fake_private_scout(
            _,
            scoped_tenant_id,
            document_ids=document_ids,
        )

    graph = build_research_graph(
        fake_research_classifier,
        fake_plan_creator,
        fake_direct_answer,
        fake_successful_search,
        scout_private_knowledge=recording_private_scout,
    )

    await graph.ainvoke(
        {
            "query": "Compare HTTP/2 and HTTP/3 using internal evidence.",
            "tenant_id": tenant_id,
            "document_ids": ["DOC-0000000000000001"],
        }
    )

    assert received_document_ids == [["DOC-0000000000000001"]]


@pytest.mark.anyio
async def test_research_graph_preserves_partial_search_results() -> None:
    graph = build_research_graph(
        fake_research_classifier,
        fake_plan_creator,
        fake_direct_answer,
        fake_partial_search,
    )

    result = await graph.ainvoke(
        {
            "query": "Compare HTTP/2 and HTTP/3 using current sources.",
            "status": "pending",
        }
    )

    assert result["status"] == "web_search_partial"

    outcomes = result["web_search_results"]

    assert outcomes[0].succeeded is True
    assert outcomes[1].succeeded is False
    assert outcomes[1].error == ("RuntimeError: simulated provider failure.")
    assert len(result["web_sources"]) == 2


@pytest.mark.anyio
async def test_research_graph_marks_total_search_failure() -> None:
    graph = build_research_graph(
        fake_research_classifier,
        fake_plan_creator,
        fake_direct_answer,
        fake_failed_search,
    )

    result = await graph.ainvoke(
        {
            "query": "Compare HTTP/2 and HTTP/3 using current sources.",
            "status": "pending",
        }
    )

    assert result["status"] == "web_search_failed"
    assert all(not outcome.succeeded for outcome in result["web_search_results"])
    assert result["web_sources"] == []


@pytest.mark.anyio
async def test_research_graph_marks_empty_search_results() -> None:
    graph = build_research_graph(
        fake_research_classifier,
        fake_plan_creator,
        fake_direct_answer,
        fake_empty_search,
    )

    result = await graph.ainvoke(
        {
            "query": "Compare HTTP/2 and HTTP/3 using current sources.",
            "status": "pending",
        }
    )

    assert result["status"] == "web_search_empty"
    assert all(outcome.succeeded for outcome in result["web_search_results"])
    assert result["web_sources"] == []


def test_default_graph_forwards_request_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm_client = Mock()
    tavily_client = Mock()
    expected_graph = Mock()
    provider_calls: list[str | None] = []

    def fake_create_llm_client(
        provider: str | None = None,
    ) -> Mock:
        provider_calls.append(provider)

        return llm_client

    def fake_tavily_client() -> Mock:
        return tavily_client

    def fake_build_research_graph(
        *_: object,
        **__: object,
    ) -> Mock:
        return expected_graph

    monkeypatch.setattr(
        graph_module,
        "create_llm_client",
        fake_create_llm_client,
    )
    monkeypatch.setattr(
        graph_module,
        "TavilySearchClient",
        fake_tavily_client,
    )
    monkeypatch.setattr(
        graph_module,
        "build_research_graph",
        fake_build_research_graph,
    )

    result = graph_module.build_default_research_graph("qwen")

    assert result is expected_graph
    assert provider_calls == [
        "qwen",
    ]


def test_client_graph_uses_canonical_eight_agent_builder_with_local_scout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm_client = Mock()
    local_scout = Mock()
    tavily_client = Mock()
    expected_graph = Mock()
    canonical_builder = Mock(return_value=expected_graph)
    legacy_builder = Mock()
    monkeypatch.setattr(
        graph_module,
        "TavilySearchClient",
        Mock(return_value=tavily_client),
    )
    monkeypatch.setattr(
        graph_module,
        "build_eight_agent_research_graph",
        canonical_builder,
    )
    monkeypatch.setattr(
        graph_module,
        "build_research_graph",
        legacy_builder,
    )

    result = graph_module.build_research_graph_for_client(
        llm_client,
        local_scout=local_scout,
    )

    assert result is expected_graph
    canonical_builder.assert_called_once()
    legacy_builder.assert_not_called()
