from collections.abc import Callable

from app.schemas.evidence import EvidenceSource
from app.services.evidence import create_mcp_evidence
from app.services.mcp.base import MCPToolClient
from app.services.mcp.http import StreamableHTTPMCPClient


class MCPReferenceScout:
    """Retrieve optional organization evidence through a real MCP tool server."""

    def __init__(
        self,
        endpoint: str,
        *,
        server_name: str = "evident-reference",
        tool_name: str = "search_research_standards",
        client_factory: Callable[[str], MCPToolClient] = StreamableHTTPMCPClient,
    ) -> None:
        normalized_endpoint = endpoint.strip()
        if not normalized_endpoint:
            raise ValueError("MCP endpoint must not be empty.")

        self._endpoint = normalized_endpoint
        self._server_name = server_name.strip()
        self._tool_name = tool_name.strip()
        self._client_factory = client_factory

        if not self._server_name or not self._tool_name:
            raise ValueError("MCP server and tool names must not be empty.")

    async def scout(self, query: str) -> list[EvidenceSource]:
        """Call the configured tool and normalize its text result as evidence."""

        client = self._client_factory(self._endpoint)
        try:
            tools = await client.list_tools()
            if self._tool_name not in {tool.name for tool in tools}:
                raise RuntimeError(
                    f"MCP server does not advertise required tool: {self._tool_name}."
                )
            result = await client.call_tool(
                self._tool_name,
                {"query": query},
            )
            return [
                create_mcp_evidence(
                    server_name=self._server_name,
                    tool_name=self._tool_name,
                    result=result,
                )
            ]
        finally:
            await client.close()
