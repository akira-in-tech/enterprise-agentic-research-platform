from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class MCPTool(BaseModel):
    """Represent one tool advertised by an MCP server."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str = Field(min_length=1, max_length=200)
    title: str | None = None
    description: str | None = None
    input_schema: dict[str, Any] = Field(alias="inputSchema")
    output_schema: dict[str, Any] | None = Field(default=None, alias="outputSchema")


class MCPContentBlock(BaseModel):
    """Represent a validated MCP tool-result content block."""

    model_config = ConfigDict(extra="allow")

    type: str = Field(min_length=1)
    text: str | None = None


class MCPToolResult(BaseModel):
    """Represent the result returned by tools/call."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    content: list[MCPContentBlock]
    structured_content: dict[str, Any] | None = Field(
        default=None,
        alias="structuredContent",
    )
    is_error: bool = Field(default=False, alias="isError")


class MCPInitializeResult(BaseModel):
    """Represent negotiated MCP server capabilities."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    protocol_version: str = Field(alias="protocolVersion")
    capabilities: dict[str, Any]
    server_info: dict[str, Any] = Field(alias="serverInfo")


class MCPListToolsResult(BaseModel):
    """Represent one page returned by tools/list."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    tools: list[MCPTool]
    next_cursor: str | None = Field(default=None, alias="nextCursor")


MCPJSONRPCVersion = Literal["2.0"]
