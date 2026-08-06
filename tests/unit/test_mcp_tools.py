from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.report import ResearchSource
from app.db.models.research import ResearchRun
from app.services.knowledge.management import KnowledgeDocumentService
from app.services.knowledge.retrieval import PrivateKnowledgeRetriever
from app.services.mcp.tools import MCPResearchTools, MCPToolError
from app.services.search.base import SearchClient, SearchResult

NULL_SESSION_FACTORY = cast(async_sessionmaker[AsyncSession], None)


class _SessionContext:
    """Yield a fixed mocked session, mirroring async_sessionmaker's contract."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *_: object) -> bool:
        return False


def make_session_factory(
    session_mock: AsyncMock,
) -> async_sessionmaker[AsyncSession]:
    session = cast(AsyncSession, session_mock)

    def factory() -> _SessionContext:
        return _SessionContext(session)

    return cast(async_sessionmaker[AsyncSession], factory)


def create_session_mock() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


class FakeWebSearchClient:
    def __init__(self, results: list[SearchResult]) -> None:
        self.results = results
        self.calls: list[tuple[str, int]] = []

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        self.calls.append((query, max_results))
        return self.results


class FakePrivateRetriever:
    def __init__(self, sources: list[object]) -> None:
        self.sources = sources
        self.calls: list[tuple[str, str, int]] = []

    async def retrieve(self, *, query: str, tenant_id: str, limit: int = 5) -> list[object]:
        self.calls.append((query, tenant_id, limit))
        return self.sources


class FakeDocumentService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def upload(self, **kwargs: object) -> object:
        self.calls.append(kwargs)

        class _Document:
            id = "DOC-0000000000000001"
            status = "ready"

        return _Document()


@pytest.mark.anyio
async def test_search_web_formats_results() -> None:
    client = FakeWebSearchClient(
        [
            SearchResult(
                title="HTTP/3 overview",
                url="https://example.com/http3",
                content="QUIC-based transport.",
                source="example.com",
            )
        ]
    )
    tools = MCPResearchTools(
        session_factory=NULL_SESSION_FACTORY,
        web_search_client=cast(SearchClient, client),
    )

    result = await tools.search_web("HTTP/3", max_results=3)

    assert "HTTP/3 overview" in result
    assert "https://example.com/http3" in result
    assert client.calls == [("HTTP/3", 3)]


@pytest.mark.anyio
async def test_search_web_raises_when_unconfigured() -> None:
    tools = MCPResearchTools(session_factory=NULL_SESSION_FACTORY)

    with pytest.raises(MCPToolError, match="not configured"):
        await tools.search_web("HTTP/3")


@pytest.mark.anyio
async def test_search_private_documents_formats_sources() -> None:
    class _Source:
        source_id = "PRIVATE-0123456789ABCDEF"
        filename = "runbook.md"
        content = "Runbook content."

    retriever = FakePrivateRetriever([_Source()])
    tools = MCPResearchTools(
        session_factory=NULL_SESSION_FACTORY,
        private_retriever=cast(PrivateKnowledgeRetriever, retriever),
    )
    tenant_id = str(uuid4())

    result = await tools.search_private_documents(tenant_id, "onboarding", max_results=2)

    assert "runbook.md" in result
    assert retriever.calls == [("onboarding", tenant_id, 2)]


@pytest.mark.anyio
async def test_search_private_documents_raises_when_unconfigured() -> None:
    tools = MCPResearchTools(session_factory=NULL_SESSION_FACTORY)

    with pytest.raises(MCPToolError, match="not configured"):
        await tools.search_private_documents(str(uuid4()), "onboarding")


@pytest.mark.anyio
async def test_retrieve_source_returns_formatted_text() -> None:
    session_mock = create_session_mock()
    factory = make_session_factory(session_mock)
    tenant_id = uuid4()
    source = ResearchSource(
        report_id=uuid4(),
        tenant_id=tenant_id,
        research_run_id=uuid4(),
        source_id="WEB-0123456789ABCDEF",
        origin="web",
        title="HTTP/3 overview",
        locator="https://example.com/http3",
        content="QUIC-based transport.",
        provider="tavily",
        relevance=0.8,
        content_quality=0.8,
        traceability=1.0,
        overall_score=0.85,
        cited=True,
    )
    session_mock.scalar.return_value = source

    tools = MCPResearchTools(session_factory=factory)

    result = await tools.retrieve_source(str(tenant_id), "WEB-0123456789ABCDEF")

    assert "WEB-0123456789ABCDEF" in result
    assert "QUIC-based transport." in result


@pytest.mark.anyio
async def test_retrieve_source_raises_when_missing() -> None:
    session_mock = create_session_mock()
    factory = make_session_factory(session_mock)
    session_mock.scalar.return_value = None

    tools = MCPResearchTools(session_factory=factory)

    with pytest.raises(MCPToolError, match="No source"):
        await tools.retrieve_source(str(uuid4()), "WEB-0123456789ABCDEF")


@pytest.mark.anyio
async def test_ingest_document_wraps_document_service() -> None:
    document_service = FakeDocumentService()
    tools = MCPResearchTools(
        session_factory=NULL_SESSION_FACTORY,
        document_service=cast(KnowledgeDocumentService, document_service),
    )
    tenant_id = str(uuid4())

    result = await tools.ingest_document(tenant_id, "Onboarding runbook", "Step one. Step two.")

    assert "DOC-0000000000000001" in result
    assert document_service.calls[0]["filename"] == "Onboarding runbook.md"
    assert document_service.calls[0]["raw_content"] == b"Step one. Step two."


@pytest.mark.anyio
async def test_ingest_document_raises_when_unconfigured() -> None:
    tools = MCPResearchTools(session_factory=NULL_SESSION_FACTORY)

    with pytest.raises(MCPToolError, match="not configured"):
        await tools.ingest_document(str(uuid4()), "Title", "Content")


@pytest.mark.anyio
async def test_save_research_report_creates_report_when_run_exists() -> None:
    session_mock = create_session_mock()
    factory = make_session_factory(session_mock)
    tenant_id = uuid4()
    run_id = uuid4()
    session_mock.scalar.return_value = ResearchRun(
        id=run_id,
        tenant_id=tenant_id,
        query="Compare HTTP/2 and HTTP/3.",
        llm_provider="anthropic",
        status="completed",
    )

    tools = MCPResearchTools(session_factory=factory)

    result = await tools.save_research_report(str(tenant_id), str(run_id), "External report body.")

    assert str(run_id) in result
    session_mock.add.assert_called_once()
    session_mock.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_save_research_report_raises_when_run_missing() -> None:
    session_mock = create_session_mock()
    factory = make_session_factory(session_mock)
    session_mock.scalar.return_value = None

    tools = MCPResearchTools(session_factory=factory)

    with pytest.raises(MCPToolError, match="No research run"):
        await tools.save_research_report(str(uuid4()), str(uuid4()), "Body.")

    session_mock.add.assert_not_called()


@pytest.mark.anyio
async def test_save_research_report_rejects_empty_content() -> None:
    tools = MCPResearchTools(session_factory=NULL_SESSION_FACTORY)

    with pytest.raises(MCPToolError, match="must not be empty"):
        await tools.save_research_report(str(uuid4()), str(uuid4()), "   ")


@pytest.mark.anyio
async def test_get_research_history_formats_runs() -> None:
    session_mock = create_session_mock()
    factory = make_session_factory(session_mock)
    tenant_id = uuid4()
    run = ResearchRun(
        id=uuid4(),
        tenant_id=tenant_id,
        query="Compare HTTP/2 and HTTP/3.",
        llm_provider="anthropic",
        status="completed",
        route="deep_research",
    )
    session_mock.scalars.return_value = [run]

    tools = MCPResearchTools(session_factory=factory)

    result = await tools.get_research_history(str(tenant_id), limit=5)

    assert "Compare HTTP/2 and HTTP/3." in result
    assert "completed" in result


@pytest.mark.anyio
async def test_request_human_review_appends_audit_event() -> None:
    session_mock = create_session_mock()
    factory = make_session_factory(session_mock)
    tenant_id = uuid4()
    run_id = uuid4()
    session_mock.scalar.return_value = ResearchRun(
        id=run_id,
        tenant_id=tenant_id,
        query="Should I invest in this fund?",
        llm_provider="anthropic",
        status="completed",
    )

    tools = MCPResearchTools(session_factory=factory)

    result = await tools.request_human_review(
        str(tenant_id),
        str(run_id),
        "Financial guidance must be reviewed by a licensed advisor.",
    )

    assert str(run_id) in result
    session_mock.add.assert_called_once()
    added_event = session_mock.add.call_args.args[0]
    assert added_event.event_type == "human_review_requested"
    session_mock.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_request_human_review_raises_when_run_missing() -> None:
    session_mock = create_session_mock()
    factory = make_session_factory(session_mock)
    session_mock.scalar.return_value = None

    tools = MCPResearchTools(session_factory=factory)

    with pytest.raises(MCPToolError, match="No research run"):
        await tools.request_human_review(str(uuid4()), str(uuid4()), "reason")


@pytest.mark.anyio
async def test_parses_invalid_tenant_id() -> None:
    tools = MCPResearchTools(session_factory=NULL_SESSION_FACTORY)

    with pytest.raises(MCPToolError, match="tenant_id must be a UUID"):
        await tools.get_research_history("not-a-uuid")
