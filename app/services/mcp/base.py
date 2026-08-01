from typing import Any, Protocol

from app.schemas.mcp import MCPTool, MCPToolResult


class MCPToolClient(Protocol):
    """Define the MCP tool operations used by the research platform."""

    async def list_tools(self) -> list[MCPTool]:
        """Discover every tool advertised by the server."""

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> MCPToolResult:
        """Invoke one advertised tool."""

    async def close(self) -> None:
        """Release the MCP transport and server session."""
