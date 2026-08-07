from collections.abc import Iterable
from hashlib import sha256

from app.schemas.evidence import EvidenceSource
from app.schemas.mcp import MCPToolResult
from app.schemas.source import PrivateSource, WebSource


def normalize_web_sources(
    sources: Iterable[WebSource],
) -> list[EvidenceSource]:
    """Convert canonical web sources into provider-neutral evidence."""

    return [
        EvidenceSource(
            source_id=source.source_id,
            origin="web",
            title=source.title,
            locator=source.url,
            content=source.content,
            provider=source.provider,
            source_type=source.source_type,
            authors=source.authors,
            year=source.year,
            venue=source.venue,
        )
        for source in sources
        if source.content.strip()
    ]


def normalize_private_sources(
    sources: Iterable[PrivateSource],
) -> list[EvidenceSource]:
    """Convert private retrieval results into provider-neutral evidence."""

    return [
        EvidenceSource(
            source_id=source.source_id,
            origin="private",
            title=source.filename,
            locator=f"{source.document_id}/{source.chunk_id}",
            content=source.content,
            provider=source.provider,
            retrieval_score=source.score,
        )
        for source in sources
    ]


def create_mcp_evidence(
    *,
    server_name: str,
    tool_name: str,
    result: MCPToolResult,
) -> EvidenceSource:
    """Convert a successful MCP text result into stable evidence."""

    if result.is_error:
        raise ValueError("MCP tool errors cannot be used as evidence.")

    normalized_server = server_name.strip()
    normalized_tool = tool_name.strip()
    text = "\n".join(
        block.text.strip()
        for block in result.content
        if block.type == "text" and block.text and block.text.strip()
    )

    if not normalized_server or not normalized_tool or not text:
        raise ValueError("MCP evidence requires server, tool, and text content.")

    digest = (
        sha256(f"{normalized_server}\0{normalized_tool}\0{text}".encode()).hexdigest()[:16].upper()
    )

    return EvidenceSource(
        source_id=f"MCP-{digest}",
        origin="mcp",
        title=f"{normalized_server}: {normalized_tool}",
        locator=f"mcp://{normalized_server}/{normalized_tool}",
        content=text,
        provider=normalized_server,
    )
