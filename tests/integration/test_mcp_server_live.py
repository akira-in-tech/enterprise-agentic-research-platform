import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

from app.core.config import settings
from app.services.mcp import StreamableHTTPMCPClient


def reserve_port() -> int:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


@pytest.mark.integration
@pytest.mark.anyio
async def test_real_mcp_server_streamable_http_round_trip() -> None:
    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    port = reserve_port()
    environment = {
        **os.environ,
        "MCP_SERVER_HOST": "127.0.0.1",
        "MCP_SERVER_PORT": str(port),
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "app.mcp_server"],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        health_url = f"http://127.0.0.1:{port}/health"
        for _ in range(50):
            try:
                with urllib.request.urlopen(health_url, timeout=0.2) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("MCP server did not become healthy.")

        client = StreamableHTTPMCPClient(f"http://127.0.0.1:{port}/mcp")
        try:
            tools = await client.list_tools()
            result = await client.call_tool(
                "search_research_standards",
                {"query": "evidence conflicts", "max_results": 2},
            )
        finally:
            await client.close()

        assert {tool.name for tool in tools} == {
            "search_research_standards",
            "search_web",
            "search_private_documents",
            "retrieve_source",
            "ingest_document",
            "save_research_report",
            "get_research_history",
            "request_human_review",
        }
        assert result.is_error is False
        assert any(block.type == "text" and block.text for block in result.content)
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
