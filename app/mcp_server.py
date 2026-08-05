import logging
import re
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from app.core.config import settings
from app.db.session import create_database_engine, create_session_factory
from app.services.embeddings.factory import ClosableEmbeddingClient, create_embedding_client
from app.services.knowledge import KnowledgeDocumentService, PostgresKnowledgeDocumentStore
from app.services.knowledge.indexing import KnowledgeIndexer
from app.services.knowledge.retrieval import PrivateKnowledgeRetriever
from app.services.mcp.tools import MCPResearchTools, MCPToolError
from app.services.search.tavily import TavilySearchClient
from app.services.storage import create_document_storage
from app.services.vector_store.factory import create_vector_store

logger = logging.getLogger(__name__)

REFERENCE_CARDS: tuple[tuple[str, str], ...] = (
    (
        "Evidence traceability",
        "A trustworthy research claim should identify its source, preserve a stable locator, "
        "and distinguish retrieved evidence from analyst interpretation.",
    ),
    (
        "Source triangulation",
        "Material conclusions should be checked across independent sources. Conflicting evidence "
        "must be surfaced rather than silently averaged or discarded.",
    ),
    (
        "Research limitations",
        "Reports should state missing evidence, freshness constraints, and unresolved uncertainty "
        "so readers can judge whether a conclusion is decision-ready.",
    ),
    (
        "Private knowledge isolation",
        "Organization knowledge retrieval must preserve tenant scope from request through storage, "
        "vector search, evidence generation, and deletion.",
    ),
)


def search_reference_cards(query: str, *, max_results: int = 3) -> str:
    """Return relevant organization research standards as plain text evidence."""

    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query must not be empty")
    if max_results < 1 or max_results > 4:
        raise ValueError("max_results must be between 1 and 4")

    query_terms = set(re.findall(r"[a-z0-9]+", normalized_query.lower()))
    ranked: list[tuple[int, int, str, str]] = []
    for index, (title, content) in enumerate(REFERENCE_CARDS):
        card_terms = set(re.findall(r"[a-z0-9]+", f"{title} {content}".lower()))
        ranked.append((len(query_terms & card_terms), -index, title, content))

    selected = sorted(ranked, reverse=True)[:max_results]
    return "\n\n".join(
        f"Reference: {title}\n{content}\nSource: Evident research standards"
        for _, _, title, content in selected
    )


def _create_embedding_client_or_none() -> ClosableEmbeddingClient | None:
    """Create the configured embedding client, or None when unavailable."""

    try:
        return create_embedding_client()
    except Exception:
        return None


def _build_research_tools(resource_stack: AsyncExitStack) -> MCPResearchTools:
    """Construct the research toolset, degrading gracefully per capability.

    Every dependency here is optional from the MCP server's point of view:
    a demo or CI environment may not have Tavily, Milvus, or PostgreSQL
    credentials configured. Each capability is attempted independently so
    one missing credential disables only its tool instead of the whole
    server. Failures are logged, not raised, matching the existing
    fail-open MCP philosophy for optional evidence sources.
    """

    engine = create_database_engine()
    resource_stack.push_async_callback(engine.dispose)
    session_factory = create_session_factory(engine)

    web_search_client: TavilySearchClient | None = None
    try:
        web_search_client = TavilySearchClient()
    except ValueError:
        logger.warning("MCP search_web tool disabled: Tavily is not configured.")

    private_retriever: PrivateKnowledgeRetriever | None = None
    document_service: KnowledgeDocumentService | None = None
    try:
        embedding_client = _create_embedding_client_or_none()
        if embedding_client is not None:
            resource_stack.push_async_callback(embedding_client.close)
            vector_store = create_vector_store(dimensions=embedding_client.dimensions)
            resource_stack.push_async_callback(vector_store.close)
            private_retriever = PrivateKnowledgeRetriever(embedding_client, vector_store)

            document_storage = create_document_storage()
            resource_stack.push_async_callback(document_storage.close)
            document_service = KnowledgeDocumentService(
                PostgresKnowledgeDocumentStore(session_factory),
                document_storage,
                KnowledgeIndexer(embedding_client, vector_store),
                vector_store,
                max_upload_bytes=settings.document_max_upload_bytes,
            )
    except Exception:
        logger.warning(
            "MCP private-knowledge tools disabled: embeddings or vector store "
            "are not configured.",
            exc_info=True,
        )

    return MCPResearchTools(
        session_factory=session_factory,
        web_search_client=web_search_client,
        private_retriever=private_retriever,
        document_service=document_service,
    )


def create_mcp_server(tools: MCPResearchTools) -> FastMCP[None]:
    """Build the Streamable HTTP research server around a fixed toolset."""

    server: FastMCP[None] = FastMCP(
        settings.mcp_server_name,
        instructions=(
            "Expose the platform's web search, private-knowledge search, evidence "
            "retrieval, document ingestion, report persistence, research history, "
            "and human-review request capabilities as MCP tools."
        ),
        host=settings.mcp_server_host,
        port=settings.mcp_server_port,
        stateless_http=True,
        json_response=True,
    )

    @server.tool(name="search_research_standards")
    def search_research_standards(query: str, max_results: int = 3) -> str:
        """Search the organization research standards reference cards."""

        return search_reference_cards(query, max_results=max_results)

    @server.tool(name="search_web")
    async def search_web(query: str, max_results: int = 5) -> str:
        """Search the public web through the platform's search provider."""

        try:
            return await tools.search_web(query, max_results=max_results)
        except MCPToolError as error:
            return f"search_web unavailable: {error}"

    @server.tool(name="search_private_documents")
    async def search_private_documents(tenant_id: str, query: str, max_results: int = 5) -> str:
        """Search one tenant's private knowledge base."""

        try:
            return await tools.search_private_documents(
                tenant_id,
                query,
                max_results=max_results,
            )
        except MCPToolError as error:
            return f"search_private_documents unavailable: {error}"

    @server.tool(name="retrieve_source")
    async def retrieve_source(
        tenant_id: str,
        source_id: str,
        research_run_id: str = "",
    ) -> str:
        """Retrieve one durable evidence source by its stable source ID."""

        try:
            return await tools.retrieve_source(
                tenant_id,
                source_id,
                research_run_id=research_run_id or None,
            )
        except MCPToolError as error:
            return f"retrieve_source failed: {error}"

    @server.tool(name="ingest_document")
    async def ingest_document(tenant_id: str, title: str, content: str) -> str:
        """Upload, index, and persist one private document from raw text."""

        try:
            return await tools.ingest_document(tenant_id, title, content)
        except MCPToolError as error:
            return f"ingest_document failed: {error}"

    @server.tool(name="save_research_report")
    async def save_research_report(tenant_id: str, research_run_id: str, content: str) -> str:
        """Attach an externally authored report to an existing research run."""

        try:
            return await tools.save_research_report(tenant_id, research_run_id, content)
        except MCPToolError as error:
            return f"save_research_report failed: {error}"

    @server.tool(name="get_research_history")
    async def get_research_history(tenant_id: str, limit: int = 10) -> str:
        """List one tenant's most recent research runs."""

        try:
            return await tools.get_research_history(tenant_id, limit=limit)
        except MCPToolError as error:
            return f"get_research_history failed: {error}"

    @server.tool(name="request_human_review")
    async def request_human_review(tenant_id: str, research_run_id: str, reason: str) -> str:
        """Request human review of one research run's conclusions."""

        try:
            return await tools.request_human_review(tenant_id, research_run_id, reason)
        except MCPToolError as error:
            return f"request_human_review failed: {error}"

    return server


_resource_stack = AsyncExitStack()
_tools = _build_research_tools(_resource_stack)
mcp = create_mcp_server(_tools)


async def health(_: Request) -> JSONResponse:
    """Expose a container health endpoint without entering the MCP protocol."""

    return JSONResponse({"status": "healthy"})


@asynccontextmanager
async def lifespan(_: Starlette) -> AsyncIterator[None]:
    """Run the official SDK session manager and dispose owned resources."""

    async with _resource_stack:
        async with mcp.session_manager.run():
            yield


app = Starlette(
    routes=[
        Route("/health", health),
        Mount("/", app=mcp.streamable_http_app()),
    ],
    lifespan=lifespan,
)


def main() -> None:
    """Run the MCP server as a standalone internal service."""

    uvicorn.run(
        app,
        host=settings.mcp_server_host,
        port=settings.mcp_server_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
