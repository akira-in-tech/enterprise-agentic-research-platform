from collections.abc import Sequence
from typing import Any, cast

import httpx
import pytest

from app.agents.web_scout import WebScoutResult
from app.mcp_server import mcp, search_reference_cards
from app.schemas.evidence import EvidenceSource
from app.schemas.mcp import MCPContentBlock, MCPTool, MCPToolResult
from app.schemas.planner import ReportSection, ResearchPlan, ResearchTask
from app.services.mcp import MCPReferenceScout, StreamableHTTPMCPClient
from app.workflow.graph import build_eight_agent_web_scout_node


class RecordingMCPClient:
    def __init__(
        self,
        *,
        tools: list[MCPTool] | None = None,
        result: MCPToolResult | None = None,
    ) -> None:
        self.tools = tools or []
        self.result = result
        self.calls: list[tuple[str, dict[str, Any] | None]] = []
        self.closed = False

    async def list_tools(self) -> list[MCPTool]:
        return self.tools

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> MCPToolResult:
        self.calls.append((name, arguments))
        if self.result is None:
            raise RuntimeError("missing test result")
        return self.result

    async def close(self) -> None:
        self.closed = True


def test_reference_search_is_bounded_and_relevant() -> None:
    result = search_reference_cards("tenant private knowledge isolation", max_results=1)

    assert "Private knowledge isolation" in result
    assert result.count("Reference:") == 1


@pytest.mark.anyio
async def test_reference_scout_normalizes_real_tool_result_and_closes() -> None:
    client = RecordingMCPClient(
        tools=[
            MCPTool(
                name="search_research_standards",
                description="Search research standards.",
                inputSchema={"type": "object"},
            )
        ],
        result=MCPToolResult(
            content=[MCPContentBlock(type="text", text="Trace every material claim.")]
        ),
    )
    scout = MCPReferenceScout(
        "http://mcp.test/mcp",
        client_factory=lambda _: client,
    )

    sources = await scout.scout("How should evidence be verified?")

    assert len(sources) == 1
    assert sources[0].origin == "mcp"
    assert sources[0].content == "Trace every material claim."
    assert client.calls == [
        (
            "search_research_standards",
            {"query": "How should evidence be verified?"},
        )
    ]
    assert client.closed is True


@pytest.mark.anyio
async def test_reference_scout_rejects_missing_tool_and_closes() -> None:
    client = RecordingMCPClient()
    scout = MCPReferenceScout(
        "http://mcp.test/mcp",
        client_factory=lambda _: client,
    )

    with pytest.raises(RuntimeError, match="does not advertise"):
        await scout.scout("evidence")

    assert client.closed is True


@pytest.mark.anyio
async def test_official_mcp_server_and_platform_client_interoperate() -> None:
    transport = httpx.ASGITransport(app=mcp.streamable_http_app())
    async with mcp.session_manager.run():
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://127.0.0.1:8001",
        ) as http_client:
            client = StreamableHTTPMCPClient(
                "http://127.0.0.1:8001/mcp",
                client=http_client,
            )
            tools = await client.list_tools()
            result = await client.call_tool(
                "search_research_standards",
                {"query": "source traceability", "max_results": 1},
            )
            await client.close()

    assert [tool.name for tool in tools] == ["search_research_standards"]
    assert result.is_error is False
    assert result.content[0].text is not None
    assert "Evidence traceability" in result.content[0].text


@pytest.mark.anyio
async def test_web_scout_federates_mcp_evidence_without_adding_an_agent() -> None:
    async def scout_web(_: Sequence[ResearchTask]) -> WebScoutResult:
        return WebScoutResult(outcomes=[], sources=[])

    async def scout_mcp(_: str) -> list[EvidenceSource]:
        return [
            EvidenceSource(
                source_id="MCP-0123456789ABCDEF",
                origin="mcp",
                title="Organization standard",
                locator="mcp://reference/search",
                content="Material claims require traceable evidence.",
                provider="reference",
            )
        ]

    plan = ResearchPlan(
        goal="Evaluate evidence controls.",
        sub_questions=["What is traceability?", "How are conflicts handled?"],
        tasks=[
            ResearchTask(
                title="Evidence controls",
                search_query="evidence traceability controls",
                rationale="Find trustworthy research controls.",
            ),
            ResearchTask(
                title="Conflict handling",
                search_query="conflicting source handling",
                rationale="Find conflict handling guidance.",
            ),
        ],
        report_outline=[
            ReportSection(title="Conclusion", purpose="State the recommendation."),
            ReportSection(title="Evidence", purpose="Explain the evidence."),
            ReportSection(title="Limits", purpose="Explain limitations."),
        ],
    )
    node = build_eight_agent_web_scout_node(scout_web, scout_mcp)

    update = await node({"query": "How should evidence be verified?", "plan": plan})

    assert update["mcp_scout_status"] == "completed"
    assert update["mcp_scout_errors"] == []
    mcp_sources = cast(list[EvidenceSource], update["mcp_sources"])
    assert [source.origin for source in mcp_sources] == ["mcp"]
