import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from app.core.config import settings

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


def create_mcp_server() -> FastMCP[None]:
    """Build the stateless Streamable HTTP reference server."""

    server: FastMCP[None] = FastMCP(
        settings.mcp_server_name,
        instructions=(
            "Expose organization research standards as optional, traceable MCP evidence."
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

    return server


mcp = create_mcp_server()


async def health(_: Request) -> JSONResponse:
    """Expose a container health endpoint without entering the MCP protocol."""

    return JSONResponse({"status": "healthy"})


@asynccontextmanager
async def lifespan(_: Starlette) -> AsyncIterator[None]:
    """Run the official SDK session manager for the ASGI server lifetime."""

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
