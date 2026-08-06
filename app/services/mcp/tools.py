from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.report import ResearchReport, ResearchSource
from app.db.models.research import ResearchRun
from app.db.repositories.durability import ResearchDurabilityRepository
from app.db.repositories.reports import ResearchReportRepository
from app.db.repositories.research_runs import ResearchRunRepository
from app.services.knowledge.management import (
    KnowledgeDocumentAlreadyExistsError,
    KnowledgeDocumentService,
)
from app.services.knowledge.retrieval import PrivateKnowledgeRetriever
from app.services.search.base import SearchClient


class MCPToolError(RuntimeError):
    """Represent a tool-execution failure that should reach the MCP caller."""


def _parse_tenant_id(tenant_id: str) -> UUID:
    try:
        return UUID(tenant_id.strip())
    except ValueError as error:
        raise MCPToolError(f"tenant_id must be a UUID; received {tenant_id!r}.") from error


def _parse_run_id(research_run_id: str) -> UUID:
    try:
        return UUID(research_run_id.strip())
    except ValueError as error:
        raise MCPToolError(
            f"research_run_id must be a UUID; received {research_run_id!r}."
        ) from error


def format_web_results(results: Sequence[object]) -> str:
    """Render Tavily search results as plain-text MCP evidence."""

    if not results:
        return "No public web results were found for this query."

    lines: list[str] = []
    for result in results:
        lines.append(
            f"Title: {result.title}\n"  # type: ignore[attr-defined]
            f"URL: {result.url}\n"  # type: ignore[attr-defined]
            f"{result.content}\n"  # type: ignore[attr-defined]
            f"Source: {result.source}"  # type: ignore[attr-defined]
        )

    return "\n\n".join(lines)


def format_private_sources(sources: Sequence[object]) -> str:
    """Render private-knowledge matches as plain-text MCP evidence."""

    if not sources:
        return "No private-knowledge matches were found for this query."

    lines: list[str] = []
    for source in sources:
        lines.append(
            f"Source: {source.source_id}\n"  # type: ignore[attr-defined]
            f"Document: {source.filename}\n"  # type: ignore[attr-defined]
            f"{source.content}"  # type: ignore[attr-defined]
        )

    return "\n\n".join(lines)


def format_research_source(source: ResearchSource) -> str:
    """Render one durable evidence source as plain-text MCP content."""

    return (
        f"Source: {source.source_id}\n"
        f"Origin: {source.origin}\n"
        f"Title: {source.title}\n"
        f"Locator: {source.locator}\n"
        f"Overall score: {source.overall_score:.2f}\n\n"
        f"{source.content}"
    )


def format_research_history(runs: Sequence[ResearchRun]) -> str:
    """Render recent research runs as plain-text MCP content."""

    if not runs:
        return "No research runs were found for this tenant."

    lines = [
        f"{run.id} | {run.status} | {run.route or 'unrouted'} | {run.query}" for run in runs
    ]

    return "\n".join(lines)


class MCPResearchTools:
    """Implement the platform's MCP research tools over existing services."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        web_search_client: SearchClient | None = None,
        private_retriever: PrivateKnowledgeRetriever | None = None,
        document_service: KnowledgeDocumentService | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._web_search_client = web_search_client
        self._private_retriever = private_retriever
        self._document_service = document_service

    async def search_web(self, query: str, *, max_results: int = 5) -> str:
        """Search the public web through the platform's Tavily provider."""

        if self._web_search_client is None:
            raise MCPToolError("Web search is not configured for this MCP server.")

        results = await self._web_search_client.search(query, max_results=max_results)

        return format_web_results(results)

    async def search_private_documents(
        self,
        tenant_id: str,
        query: str,
        *,
        max_results: int = 5,
    ) -> str:
        """Search one tenant's private knowledge base."""

        if self._private_retriever is None:
            raise MCPToolError("Private-knowledge search is not configured for this MCP server.")

        _parse_tenant_id(tenant_id)
        sources = await self._private_retriever.retrieve(
            query=query,
            tenant_id=tenant_id.strip(),
            limit=max_results,
        )

        return format_private_sources(sources)

    async def retrieve_source(
        self,
        tenant_id: str,
        source_id: str,
        *,
        research_run_id: str | None = None,
    ) -> str:
        """Retrieve one durable evidence source by its stable ID."""

        parsed_tenant_id = _parse_tenant_id(tenant_id)
        parsed_run_id = _parse_run_id(research_run_id) if research_run_id else None

        async with self._session_factory() as session:
            repository = ResearchReportRepository(session)
            source = await repository.get_source_by_id(
                tenant_id=parsed_tenant_id,
                source_id=source_id.strip(),
                research_run_id=parsed_run_id,
            )

        if source is None:
            raise MCPToolError(f"No source {source_id!r} was found for this tenant.")

        return format_research_source(source)

    async def ingest_document(
        self,
        tenant_id: str,
        title: str,
        content: str,
    ) -> str:
        """Upload, index, and persist one private document from raw text."""

        if self._document_service is None:
            raise MCPToolError("Document ingestion is not configured for this MCP server.")

        parsed_tenant_id = _parse_tenant_id(tenant_id)
        normalized_title = title.strip() or "untitled"

        try:
            document = await self._document_service.upload(
                tenant_id=parsed_tenant_id,
                uploaded_by_user_id=None,
                filename=f"{normalized_title}.md",
                declared_media_type=None,
                raw_content=content.encode("utf-8"),
            )
        except KnowledgeDocumentAlreadyExistsError as error:
            raise MCPToolError(str(error)) from error

        return (
            f"Document {document.id} ingested and indexed as {document.status} "
            f"for tenant {tenant_id}."
        )

    async def save_research_report(
        self,
        tenant_id: str,
        research_run_id: str,
        content: str,
    ) -> str:
        """Attach an externally authored report to an existing research run.

        Only usable when the run has no report yet: automated workflow
        reports always include their own citation audit and evidence
        sources, and this tool intentionally cannot overwrite one.
        """

        parsed_tenant_id = _parse_tenant_id(tenant_id)
        parsed_run_id = _parse_run_id(research_run_id)
        normalized_content = content.strip()

        if not normalized_content:
            raise MCPToolError("content must not be empty.")

        async with self._session_factory() as session:
            run_repository = ResearchRunRepository(session)
            run = await run_repository.get_for_tenant(
                tenant_id=parsed_tenant_id,
                research_run_id=parsed_run_id,
            )

            if run is None:
                raise MCPToolError(
                    f"No research run {research_run_id!r} was found for this tenant."
                )

            report = ResearchReport(
                tenant_id=parsed_tenant_id,
                research_run_id=parsed_run_id,
                content=normalized_content,
                workflow_status="externally_submitted",
                citation_valid=False,
                citation_coverage=0.0,
                reflection_status="revise",
                reflection_reasons=[
                    "Report submitted directly through MCP without automated"
                    " citation or evidence review."
                ],
                reflection_attempts=0,
            )
            session.add(report)

            try:
                await session.commit()
            except IntegrityError as error:
                await session.rollback()
                raise MCPToolError(
                    f"Research run {research_run_id!r} already has a report."
                ) from error

        return f"Report saved for research run {research_run_id}. Treat it as unreviewed evidence."

    async def get_research_history(self, tenant_id: str, *, limit: int = 10) -> str:
        """List one tenant's most recent research runs."""

        parsed_tenant_id = _parse_tenant_id(tenant_id)

        async with self._session_factory() as session:
            repository = ResearchRunRepository(session)
            runs = await repository.list_recent_for_tenant(
                tenant_id=parsed_tenant_id,
                limit=limit,
            )

        return format_research_history(runs)

    async def request_human_review(
        self,
        tenant_id: str,
        research_run_id: str,
        reason: str,
    ) -> str:
        """Record that a research run's conclusions require human review."""

        parsed_tenant_id = _parse_tenant_id(tenant_id)
        parsed_run_id = _parse_run_id(research_run_id)
        normalized_reason = reason.strip()

        if not normalized_reason:
            raise MCPToolError("reason must not be empty.")

        async with self._session_factory() as session:
            run_repository = ResearchRunRepository(session)
            run = await run_repository.get_for_tenant(
                tenant_id=parsed_tenant_id,
                research_run_id=parsed_run_id,
            )

            if run is None:
                raise MCPToolError(
                    f"No research run {research_run_id!r} was found for this tenant."
                )

            durability_repository = ResearchDurabilityRepository(session)
            await durability_repository.append_audit_event(
                tenant_id=parsed_tenant_id,
                research_run_id=parsed_run_id,
                event_type="human_review_requested",
                actor_type="user",
                details={"reason": normalized_reason},
            )
            await session.commit()

        return (
            f"Human review requested for research run {research_run_id}. "
            "This run's conclusions should not be treated as an unqualified "
            "final decision until a human reviews it."
        )
