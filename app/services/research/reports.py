from collections.abc import Callable
from typing import Literal, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import ResearchReportRepository
from app.schemas.report import ResearchReportResponse, ResearchReportSourceResponse
from app.services.research.postgres import TransactionalSessionFactory


class PostgresResearchReportStore:
    """Read durable tenant-scoped reports using short transactions."""

    def __init__(
        self,
        session_factory: TransactionalSessionFactory,
        repository_factory: Callable[
            [AsyncSession], ResearchReportRepository
        ] = ResearchReportRepository,
    ) -> None:
        self._session_factory = session_factory
        self._repository_factory = repository_factory

    async def get(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> ResearchReportResponse | None:
        """Return one report with stable evidence-source ordering."""

        async with self._session_factory.begin() as session:
            repository = self._repository_factory(session)
            report = await repository.get_for_run(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
            )

            if report is None:
                return None

            sources = await repository.list_sources_for_run(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
            )

            return ResearchReportResponse(
                report_id=report.id,
                research_run_id=report.research_run_id,
                content=report.content,
                workflow_status=report.workflow_status,
                citation_valid=report.citation_valid,
                citation_coverage=report.citation_coverage,
                reflection_status=cast(
                    Literal["approved", "revise"],
                    report.reflection_status,
                ),
                reflection_reasons=list(report.reflection_reasons),
                reflection_attempts=report.reflection_attempts,
                created_at=report.created_at,
                sources=[ResearchReportSourceResponse.model_validate(source) for source in sources],
            )

    async def list_sources(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> list[ResearchReportSourceResponse] | None:
        """Return evidence sources only when the tenant-owned report exists."""

        async with self._session_factory.begin() as session:
            repository = self._repository_factory(session)
            report = await repository.get_for_run(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
            )
            if report is None:
                return None
            sources = await repository.list_sources_for_run(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
            )
            return [ResearchReportSourceResponse.model_validate(source) for source in sources]
