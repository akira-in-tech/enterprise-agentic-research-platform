from typing import Any, cast

import httpx
from pydantic import ValidationError

from app.schemas.mcp import (
    MCPInitializeResult,
    MCPListToolsResult,
    MCPTool,
    MCPToolResult,
)

MCP_PROTOCOL_VERSION = "2025-11-25"


class MCPClientError(RuntimeError):
    """Represent an MCP transport or response validation failure."""


class MCPProtocolError(MCPClientError):
    """Represent a JSON-RPC error returned by an MCP server."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"MCP error {code}: {message}")
        self.code = code
        self.message = message


class StreamableHTTPMCPClient:
    """Provide the JSON response subset of MCP Streamable HTTP transport."""

    def __init__(
        self,
        endpoint: str,
        *,
        client: httpx.AsyncClient | None = None,
        client_name: str = "enterprise-agentic-research-platform",
        client_version: str = "0.1.0",
        timeout_seconds: float = 30.0,
    ) -> None:
        normalized_endpoint = endpoint.strip()

        if not normalized_endpoint:
            raise ValueError("MCP endpoint must not be empty.")

        self._endpoint = normalized_endpoint
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._owns_client = client is None
        self._client_name = client_name
        self._client_version = client_version
        self._request_id = 0
        self._session_id: str | None = None
        self._initialized = False

    async def initialize(self) -> MCPInitializeResult:
        """Negotiate protocol capabilities and complete MCP initialization."""

        if self._initialized:
            raise MCPClientError("MCP client is already initialized.")

        result, response = await self._request(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": self._client_name,
                    "version": self._client_version,
                },
            },
            include_protocol_header=False,
        )

        try:
            initialization = MCPInitializeResult.model_validate(result)
        except ValidationError as error:
            raise MCPClientError("MCP initialize result is invalid.") from error

        if initialization.protocol_version != MCP_PROTOCOL_VERSION:
            raise MCPClientError(
                "MCP server negotiated unsupported protocol version "
                f"{initialization.protocol_version}."
            )

        self._session_id = response.headers.get("Mcp-Session-Id")
        self._initialized = True

        try:
            await self._notify("notifications/initialized")
        except Exception:
            self._initialized = False
            raise

        return initialization

    async def list_tools(self) -> list[MCPTool]:
        """Return all tools, following MCP cursor pagination."""

        await self._ensure_initialized()
        tools: list[MCPTool] = []
        cursor: str | None = None

        while True:
            params = {"cursor": cursor} if cursor is not None else None
            result, _ = await self._request("tools/list", params)

            try:
                page = MCPListToolsResult.model_validate(result)
            except ValidationError as error:
                raise MCPClientError("MCP tools/list result is invalid.") from error

            tools.extend(page.tools)
            cursor = page.next_cursor

            if cursor is None:
                return tools

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> MCPToolResult:
        """Invoke one MCP tool and validate its result."""

        normalized_name = name.strip()

        if not normalized_name:
            raise ValueError("MCP tool name must not be empty.")

        await self._ensure_initialized()
        result, _ = await self._request(
            "tools/call",
            {
                "name": normalized_name,
                "arguments": arguments or {},
            },
        )

        try:
            return MCPToolResult.model_validate(result)
        except ValidationError as error:
            raise MCPClientError("MCP tools/call result is invalid.") from error

    async def close(self) -> None:
        """Terminate the MCP session when supported and close owned transport."""

        try:
            if self._session_id is not None:
                response = await self._client.delete(
                    self._endpoint,
                    headers=self._headers(),
                )

                if response.status_code not in {200, 202, 204, 405}:
                    response.raise_for_status()
        finally:
            self._session_id = None
            self._initialized = False

            if self._owns_client:
                await self._client.aclose()

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            await self.initialize()

    async def _request(
        self,
        method: str,
        params: dict[str, Any] | None,
        *,
        include_protocol_header: bool = True,
    ) -> tuple[dict[str, Any], httpx.Response]:
        self._request_id += 1
        request_id = self._request_id
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }

        if params is not None:
            payload["params"] = params

        response = await self._client.post(
            self._endpoint,
            json=payload,
            headers=self._headers(include_protocol_header=include_protocol_header),
        )
        response.raise_for_status()

        try:
            body = cast(dict[str, Any], response.json())
        except ValueError as error:
            raise MCPClientError("MCP server returned a non-JSON response.") from error

        if body.get("jsonrpc") != "2.0" or body.get("id") != request_id:
            raise MCPClientError("MCP server returned a mismatched JSON-RPC response.")

        protocol_error = body.get("error")

        if isinstance(protocol_error, dict):
            code = protocol_error.get("code")
            message = protocol_error.get("message")

            if isinstance(code, int) and isinstance(message, str):
                raise MCPProtocolError(code, message)

            raise MCPClientError("MCP server returned an invalid JSON-RPC error.")

        result = body.get("result")

        if not isinstance(result, dict):
            raise MCPClientError("MCP server returned no JSON-RPC result object.")

        return cast(dict[str, Any], result), response

    async def _notify(self, method: str) -> None:
        response = await self._client.post(
            self._endpoint,
            json={
                "jsonrpc": "2.0",
                "method": method,
            },
            headers=self._headers(),
        )
        response.raise_for_status()

    def _headers(self, *, include_protocol_header: bool = True) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }

        if include_protocol_header:
            headers["MCP-Protocol-Version"] = MCP_PROTOCOL_VERSION

        if self._session_id is not None:
            headers["Mcp-Session-Id"] = self._session_id

        return headers
