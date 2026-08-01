from app.schemas.mcp import MCPContentBlock, MCPToolResult
from app.schemas.source import PrivateSource, WebSource
from app.services.evidence import (
    CitationValidator,
    EvidenceScorer,
    create_mcp_evidence,
    normalize_private_sources,
    normalize_web_sources,
)


def test_evidence_normalization_and_scoring_supports_all_origins() -> None:
    web = WebSource(
        source_id="WEB-0123456789ABCDEF",
        title="HTTP/3 and QUIC",
        url="https://example.com/http3",
        content="HTTP/3 uses QUIC to reduce transport handshake latency." * 10,
        provider="fixture",
    )
    private = PrivateSource(
        source_id="PRIVATE-FEDCBA9876543210",
        document_id="DOC-0123456789ABCDEF",
        chunk_id="CHK-0123456789ABCDEF",
        filename="networking.md",
        media_type="text/markdown",
        content="Internal guidance explains HTTP/3 deployment over QUIC.",
        score=0.8,
    )
    mcp = create_mcp_evidence(
        server_name="network-observability",
        tool_name="query_metrics",
        result=MCPToolResult(
            content=[
                MCPContentBlock(
                    type="text",
                    text="QUIC handshake latency is 18 ms.",
                )
            ],
        ),
    )
    sources = [
        *normalize_web_sources([web]),
        *normalize_private_sources([private]),
        mcp,
    ]

    scores = EvidenceScorer().score(
        query="Compare HTTP/3 QUIC handshake latency",
        sources=sources,
    )

    assert [source.origin for source in sources] == ["web", "private", "mcp"]
    assert mcp.source_id.startswith("MCP-")
    assert all(0.0 <= score.overall <= 1.0 for score in scores)
    assert scores[0].relevance > 0.0
    assert scores[1].relevance >= 0.9


def test_citation_validator_reports_unknown_and_uncited_claims() -> None:
    source = normalize_web_sources(
        [
            WebSource(
                source_id="WEB-0123456789ABCDEF",
                title="HTTP/3",
                url="https://example.com/http3",
                content="HTTP/3 uses QUIC.",
                provider="fixture",
            )
        ]
    )[0]
    audit = CitationValidator().validate(
        report=(
            "HTTP/3 uses QUIC. [WEB-0123456789ABCDEF]\n\n"
            "This paragraph makes another factual claim without evidence.\n\n"
            "A fake source is cited here. [WEB-FFFFFFFFFFFFFFFF]"
        ),
        sources=[source],
    )

    assert audit.valid is False
    assert audit.coverage_ratio == 0.6667
    assert audit.unknown_source_ids == ["WEB-FFFFFFFFFFFFFFFF"]
    assert audit.uncited_claims == ["This paragraph makes another factual claim without evidence."]


def test_citation_validator_approves_fully_cited_report() -> None:
    source = normalize_web_sources(
        [
            WebSource(
                source_id="WEB-0123456789ABCDEF",
                title="HTTP/3",
                url="https://example.com/http3",
                content="HTTP/3 uses QUIC.",
                provider="fixture",
            )
        ]
    )[0]

    audit = CitationValidator().validate(
        report="HTTP/3 uses QUIC for transport. [WEB-0123456789ABCDEF]",
        sources=[source],
    )

    assert audit.valid is True
    assert audit.coverage_ratio == 1.0
