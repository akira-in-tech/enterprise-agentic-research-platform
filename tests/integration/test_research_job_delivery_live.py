import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete

from app.core.config import settings
from app.db.models import ResearchRun, ResearchWorkerLease, Tenant, User
from app.db.repositories import (
    ResearchDurabilityRepository,
    ResearchRunRepository,
    TenantRepository,
    UserRepository,
)
from app.db.session import create_database_engine, create_session_factory
from app.schemas.evidence import (
    CitationAudit,
    EvidenceScore,
    EvidenceSource,
    ReflectionDecision,
)
from app.services.cache import RedisConnection, RedisResearchProgressStore
from app.services.research.execution import ResearchExecutionService
from app.services.research.jobs import ResearchJobManager
from app.services.research.postgres import (
    PostgresResearchDurabilityStore,
    PostgresResearchRunStore,
)
from app.services.research.reports import PostgresResearchReportStore
from app.workflow.state import ResearchState

pytestmark = pytest.mark.integration


class BackgroundEvidenceWorkflow:
    async def ainvoke(self, state: ResearchState) -> ResearchState:
        source = EvidenceSource(
            source_id="WEB-0123456789ABCDEF",
            origin="web",
            title="Async delivery evidence",
            locator="https://example.com/async",
            content="Background research evidence.",
            provider="fixture",
        )
        score = EvidenceScore(
            source_id=source.source_id,
            relevance=0.9,
            content_quality=0.8,
            traceability=1,
            overall=0.88,
        )
        report = f"Background report. [{source.source_id}]"

        return {
            "query": state["query"],
            "route": "deep_research",
            "status": "research_report_completed",
            "answer": report,
            "report": report,
            "evidence_sources": [source],
            "evidence_scores": [score],
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
async def test_job_manager_delivers_progress_and_durable_report() -> None:
    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    engine = create_database_engine(echo=False)
    session_factory = create_session_factory(engine)
    redis_connection = RedisConnection.from_url()
    progress_store = RedisResearchProgressStore(redis_connection)
    tenant_id: UUID | None = None
    research_run_id: UUID | None = None
    manager: ResearchJobManager | None = None

    try:
        async with session_factory.begin() as session:
            suffix = uuid4().hex[:12]
            tenant = await TenantRepository(session).create(
                slug=f"async-report-{suffix}",
                name="Async Report Integration Test",
            )
            user = await UserRepository(session).create(
                tenant_id=tenant.id,
                email=f"async-{suffix}@example.com",
                display_name="Async Integration User",
            )
            tenant_id = tenant.id
            user_id = user.id

        workflow = BackgroundEvidenceWorkflow()
        executor = ResearchExecutionService(
            PostgresResearchRunStore(session_factory),
            lambda _: workflow,
            progress_store=progress_store,
        )
        manager = ResearchJobManager(
            executor,
            PostgresResearchDurabilityStore(session_factory),
            worker_id="integration-worker",
        )
        research_run_id = await manager.submit(
            tenant_id=tenant_id,
            requested_by_user_id=user_id,
            query="Produce a durable background report.",
            llm_provider="qwen",
        )

        async with session_factory() as session:
            queued_run = await ResearchRunRepository(session).get_for_tenant(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
            )

        assert queued_run is not None

        for _ in range(100):
            progress = await progress_store.get(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
            )
            if progress is not None and progress.status in {"completed", "failed"}:
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("Background research did not reach a terminal state.")

        assert progress is not None
        assert progress.status == "completed"
        report = await PostgresResearchReportStore(session_factory).get(
            tenant_id=tenant_id,
            research_run_id=research_run_id,
        )
        assert report is not None
        assert report.content == "Background report. [WEB-0123456789ABCDEF]"
        assert report.reflection_attempts == 1

        for _ in range(100):
            async with session_factory() as session:
                durability = ResearchDurabilityRepository(session)
                latest_checkpoint = await durability.get_latest_checkpoint(
                    tenant_id=tenant_id,
                    research_run_id=research_run_id,
                )
                audit_events = await durability.list_audit_events(
                    tenant_id=tenant_id,
                    research_run_id=research_run_id,
                )
                lease = await session.get(
                    ResearchWorkerLease,
                    (tenant_id, research_run_id),
                )
            if latest_checkpoint is not None and lease is None:
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("Durable worker ownership was not released.")

        assert latest_checkpoint is not None
        assert latest_checkpoint.sequence == 1
        assert latest_checkpoint.node_name == "completed"
        assert [event.event_type for event in audit_events] == [
            "worker.claimed",
            "worker.completed",
        ]
    finally:
        if manager is not None:
            await manager.close()
        if tenant_id is not None and research_run_id is not None:
            await progress_store.delete(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
            )
        if tenant_id is not None:
            async with session_factory.begin() as session:
                await session.execute(delete(ResearchRun).where(ResearchRun.tenant_id == tenant_id))
                await session.execute(delete(User).where(User.tenant_id == tenant_id))
                await session.execute(delete(Tenant).where(Tenant.id == tenant_id))

        await redis_connection.close()
        await engine.dispose()
