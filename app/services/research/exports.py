from typing import Literal
from uuid import UUID

from app.services.storage.base import DocumentStorage

ExportFormat = Literal["markdown", "pdf"]
CitationStyle = Literal["numbered", "footnote"]


class ResearchReportExportService:
    """Store and retrieve durable report snapshots as object-storage artifacts.

    This is separate from the research_reports database row: the database
    row is the live, queryable source of truth, while an export is an
    immutable snapshot artifact suitable for sharing or download outside
    the API, using the same DocumentStorage interface (local filesystem or
    S3) already used for uploaded private-knowledge source objects.
    """

    def __init__(self, storage: DocumentStorage) -> None:
        self._storage = storage

    @staticmethod
    def build_key(
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        format: ExportFormat = "markdown",
        citation_style: CitationStyle = "numbered",
    ) -> str:
        """Build the deterministic storage key for one run's report export."""

        extension = "pdf" if format == "pdf" else "md"
        return (
            f"tenants/{tenant_id}/report-exports/{research_run_id}/"
            f"report-{citation_style}.{extension}"
        )

    async def export(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        content: bytes,
        format: ExportFormat = "markdown",
        citation_style: CitationStyle = "numbered",
    ) -> str:
        """Store one rendered report snapshot and return its storage key."""

        if not content:
            raise ValueError("content must not be empty.")

        key = self.build_key(
            tenant_id=tenant_id,
            research_run_id=research_run_id,
            format=format,
            citation_style=citation_style,
        )
        await self._storage.put(key=key, content=content)
        return key

    async def retrieve(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        format: ExportFormat = "markdown",
        citation_style: CitationStyle = "numbered",
    ) -> bytes:
        """Read back one previously exported report snapshot."""

        key = self.build_key(
            tenant_id=tenant_id,
            research_run_id=research_run_id,
            format=format,
            citation_style=citation_style,
        )
        return await self._storage.get(key=key)
