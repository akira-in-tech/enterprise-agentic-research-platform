import json

import httpx
import pytest

from app.services.mcp import MCPProtocolError, StreamableHTTPMCPClient


@pytest.mark.anyio
async def test_mcp_client_initializes_lists_pages_calls_and_closes() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)

        if request.method == "DELETE":
            assert request.headers["Mcp-Session-Id"] == "session-123"
            return httpx.Response(204)

        body = json.loads(request.content)
        method = body["method"]

        if method == "initialize":
            assert "MCP-Protocol-Version" not in request.headers
            return httpx.Response(
                200,
                headers={"Mcp-Session-Id": "session-123"},
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "fixture", "version": "1.0"},
                    },
                },
            )

        assert request.headers["MCP-Protocol-Version"] == "2025-11-25"
        assert request.headers["Mcp-Session-Id"] == "session-123"

        if method == "notifications/initialized":
            assert "id" not in body
            return httpx.Response(202)

        if method == "tools/list":
            cursor = body.get("params", {}).get("cursor")
            tool_name = "search" if cursor is None else "fetch"
            result: dict[str, object] = {
                "tools": [
                    {
                        "name": tool_name,
                        "description": f"{tool_name} evidence",
                        "inputSchema": {"type": "object"},
                    }
                ]
            }

            if cursor is None:
                result["nextCursor"] = "next-page"

            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": body["id"], "result": result},
            )

        assert method == "tools/call"
        assert body["params"] == {
            "name": "search",
            "arguments": {"query": "HTTP/3"},
        }
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": {
                    "content": [{"type": "text", "text": "HTTP/3 uses QUIC."}],
                    "structuredContent": {"transport": "QUIC"},
                    "isError": False,
                },
            },
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = StreamableHTTPMCPClient(
            "https://mcp.example.test/mcp",
            client=http_client,
        )
        tools = await client.list_tools()
        result = await client.call_tool("search", {"query": "HTTP/3"})
        await client.close()

    assert [tool.name for tool in tools] == ["search", "fetch"]
    assert result.content[0].text == "HTTP/3 uses QUIC."
    assert result.structured_content == {"transport": "QUIC"}
    assert [request.method for request in requests].count("POST") == 5
    assert requests[-1].method == "DELETE"


@pytest.mark.anyio
async def test_mcp_client_raises_protocol_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)

        if body["method"] == "initialize":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "fixture", "version": "1.0"},
                    },
                },
            )

        if body["method"] == "notifications/initialized":
            return httpx.Response(202)

        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "error": {"code": -32602, "message": "Unknown tool"},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = StreamableHTTPMCPClient(
            "https://mcp.example.test/mcp",
            client=http_client,
        )

        with pytest.raises(MCPProtocolError, match="Unknown tool"):
            await client.call_tool("missing")
