from pathlib import Path
from uuid import uuid4

import pytest

from app.services.research.exports import ResearchReportExportService
from app.services.storage import LocalDocumentStorage
from app.services.storage.base import DocumentStorageError


@pytest.mark.anyio
async def test_export_and_retrieve_round_trip(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)
    service = ResearchReportExportService(storage)
    tenant_id = uuid4()
    research_run_id = uuid4()

    key = await service.export(
        tenant_id=tenant_id,
        research_run_id=research_run_id,
        content="# Report\n\nHTTP/3 evidence. [WEB-0123456789ABCDEF]",
    )

    assert key == f"tenants/{tenant_id}/report-exports/{research_run_id}/report.md"
    assert (tmp_path / key).exists()

    retrieved = await service.retrieve(tenant_id=tenant_id, research_run_id=research_run_id)

    assert retrieved == "# Report\n\nHTTP/3 evidence. [WEB-0123456789ABCDEF]"


@pytest.mark.anyio
async def test_export_rejects_empty_content(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)
    service = ResearchReportExportService(storage)

    with pytest.raises(ValueError, match="must not be empty"):
        await service.export(
            tenant_id=uuid4(),
            research_run_id=uuid4(),
            content="   ",
        )


@pytest.mark.anyio
async def test_export_is_tenant_and_run_scoped(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)
    service = ResearchReportExportService(storage)
    research_run_id = uuid4()

    await service.export(
        tenant_id=uuid4(),
        research_run_id=research_run_id,
        content="Tenant A report.",
    )

    with pytest.raises(DocumentStorageError):
        await service.retrieve(tenant_id=uuid4(), research_run_id=research_run_id)
