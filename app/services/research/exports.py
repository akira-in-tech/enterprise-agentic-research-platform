from uuid import UUID

from app.services.storage.base import DocumentStorage


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
    def build_key(*, tenant_id: UUID, research_run_id: UUID) -> str:
        """Build the deterministic storage key for one run's report export."""

        return f"tenants/{tenant_id}/report-exports/{research_run_id}/report.md"

    async def export(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        content: str,
    ) -> str:
        """Store one report snapshot and return its storage key."""

        normalized_content = content.strip()

        if not normalized_content:
            raise ValueError("content must not be empty.")

        key = self.build_key(tenant_id=tenant_id, research_run_id=research_run_id)
        await self._storage.put(key=key, content=normalized_content.encode("utf-8"))
        return key

    async def retrieve(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> str:
        """Read back one previously exported report snapshot."""

        key = self.build_key(tenant_id=tenant_id, research_run_id=research_run_id)
        content = await self._storage.get(key=key)
        return content.decode("utf-8")
