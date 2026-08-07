from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete

from app.core.config import settings
from app.db.models import ResearchRun, Tenant, User
from app.db.repositories import TenantRepository, UserRepository
from app.db.session import create_database_engine, create_session_factory
from app.schemas.evidence import (
    CitationAudit,
    EvidenceScore,
    EvidenceSource,
    ReflectionDecision,
)
from app.services.research.execution import ResearchExecutionService
from app.services.research.exports import ResearchReportExportService
from app.services.research.postgres import PostgresResearchRunStore
from app.services.research.reports import PostgresResearchReportStore
from app.services.storage import LocalDocumentStorage
from app.workflow.state import ResearchState

pytestmark = pytest.mark.integration


class EvidenceReportWorkflow:
    async def ainvoke(self, state: ResearchState) -> ResearchState:
        source = EvidenceSource(
            source_id="WEB-0123456789ABCDEF",
            origin="web",
            title="HTTP specification",
            locator="https://example.com/http",
            content="HTTP transport evidence.",
            provider="fixture",
        )
        return {
            "query": state["query"],
            "route": "deep_research",
            "route_reason": "Current evidence is required.",
            "status": "research_report_completed",
            "answer": f"HTTP report. [{source.source_id}]",
            "report": f"HTTP report. [{source.source_id}]",
            "evidence_sources": [source],
            "evidence_scores": [
                EvidenceScore(
                    source_id=source.source_id,
                    relevance=0.9,
                    content_quality=0.8,
                    traceability=1,
                    overall=0.88,
                )
            ],
            "citation_audit": CitationAudit(
                valid=True,
                cited_source_ids=[source.source_id],
                unknown_source_ids=[],
                uncited_claims=[],
                coverage_ratio=1,
            ),
            "reflection": ReflectionDecision(
                status="approved",
                reasons=[],
                evidence_count=1,
                average_evidence_score=0.88,
            ),
            "reflection_attempts": 1,
        }

    async def close(self) -> None:
        return None


@pytest.mark.anyio
async def test_report_export_round_trips_a_live_postgres_report(tmp_path: Path) -> None:
    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    engine = create_database_engine(echo=False)
    session_factory = create_session_factory(engine)
    tenant_id: UUID | None = None

    try:
        async with session_factory.begin() as session:
            suffix = uuid4().hex[:12]
            tenant = await TenantRepository(session).create(
                slug=f"report-export-{suffix}",
                name="Report Export Integration Test",
            )
            user = await UserRepository(session).create(
                tenant_id=tenant.id,
                email=f"report-export-{suffix}@example.com",
                password_hash="test-password-hash",
                display_name="Report Export Integration User",
            )
            tenant_id = tenant.id
            user_id = user.id

        workflow = EvidenceReportWorkflow()
        execution_service = ResearchExecutionService(
            PostgresResearchRunStore(session_factory),
            lambda _: workflow,
        )
        result = await execution_service.execute(
            tenant_id=tenant_id,
            requested_by_user_id=user_id,
            query="Compare current HTTP transports.",
            llm_provider="qwen",
        )

        report_store = PostgresResearchReportStore(session_factory)
        report = await report_store.get(
            tenant_id=tenant_id,
            research_run_id=result.research_run_id,
        )
        assert report is not None

        export_service = ResearchReportExportService(LocalDocumentStorage(tmp_path))
        storage_key = await export_service.export(
            tenant_id=tenant_id,
            research_run_id=result.research_run_id,
            content=report.content.encode("utf-8"),
        )
        retrieved_content = await export_service.retrieve(
            tenant_id=tenant_id,
            research_run_id=result.research_run_id,
        )

        assert storage_key == (
            f"tenants/{tenant_id}/report-exports/{result.research_run_id}/report-numbered.md"
        )
        assert retrieved_content.decode("utf-8") == report.content
        assert report.content == "HTTP report. [WEB-0123456789ABCDEF]"
    finally:
        if tenant_id is not None:
            async with session_factory.begin() as session:
                await session.execute(delete(ResearchRun).where(ResearchRun.tenant_id == tenant_id))
                await session.execute(delete(User).where(User.tenant_id == tenant_id))
                await session.execute(delete(Tenant).where(Tenant.id == tenant_id))

        await engine.dispose()
