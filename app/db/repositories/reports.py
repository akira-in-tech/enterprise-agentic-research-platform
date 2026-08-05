from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ResearchReport, ResearchSource
from app.schemas.evidence import EvidenceScore, EvidenceSource
from app.workflow.state import ResearchState


class ResearchReportRepository:
    """Persist and retrieve tenant-scoped research report artifacts."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_from_state(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        state: ResearchState,
    ) -> ResearchReport | None:
        """Create one report and its evidence rows without committing."""

        report_content = state.get("report")
        citation_audit = state.get("citation_audit")
        reflection = state.get("reflection")

        if report_content is None:
            return None

        if citation_audit is None or reflection is None:
            raise ValueError("Research reports require citation and reflection results.")

        report = ResearchReport(
            tenant_id=tenant_id,
            research_run_id=research_run_id,
            content=report_content,
            workflow_status=state.get("status", "research_report_completed"),
            citation_valid=citation_audit.valid,
            citation_coverage=citation_audit.coverage_ratio,
            reflection_status=reflection.status,
            reflection_reasons=list(reflection.reasons),
            reflection_attempts=state.get("reflection_attempts", 1),
        )
        self._session.add(report)
        await self._session.flush()

        scores = {score.source_id: score for score in state.get("evidence_scores", [])}
        cited_ids = set(citation_audit.cited_source_ids)

        for source in state.get("evidence_sources", []):
            score = self._require_score(source, scores)
            self._session.add(
                ResearchSource(
                    report_id=report.id,
                    tenant_id=tenant_id,
                    research_run_id=research_run_id,
                    source_id=source.source_id,
                    origin=source.origin,
                    title=source.title,
                    locator=source.locator,
                    content=source.content,
                    provider=source.provider,
                    relevance=score.relevance,
                    content_quality=score.content_quality,
                    traceability=score.traceability,
                    overall_score=score.overall,
                    cited=source.source_id in cited_ids,
                )
            )

        await self._session.flush()
        return report

    async def get_for_run(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> ResearchReport | None:
        """Return a report only when it belongs to the tenant."""

        result = await self._session.scalar(
            select(ResearchReport).where(
                ResearchReport.tenant_id == tenant_id,
                ResearchReport.research_run_id == research_run_id,
            )
        )

        return result

    async def list_sources_for_run(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> list[ResearchSource]:
        """Return evidence rows in stable source-ID order."""

        result = await self._session.scalars(
            select(ResearchSource)
            .where(
                ResearchSource.tenant_id == tenant_id,
                ResearchSource.research_run_id == research_run_id,
            )
            .order_by(ResearchSource.source_id)
        )
        return list(result)

    async def get_source_by_id(
        self,
        *,
        tenant_id: UUID,
        source_id: str,
        research_run_id: UUID | None = None,
    ) -> ResearchSource | None:
        """Return the most recent tenant-scoped source with this source ID."""

        conditions = [
            ResearchSource.tenant_id == tenant_id,
            ResearchSource.source_id == source_id,
        ]

        if research_run_id is not None:
            conditions.append(ResearchSource.research_run_id == research_run_id)

        result = await self._session.scalar(
            select(ResearchSource).where(*conditions).order_by(ResearchSource.id.desc()).limit(1)
        )

        return result

    @staticmethod
    def _require_score(
        source: EvidenceSource,
        scores: dict[str, EvidenceScore],
    ) -> EvidenceScore:
        try:
            return scores[source.source_id]
        except KeyError as error:
            raise ValueError(
                f"Evidence source {source.source_id} is missing a quality score."
            ) from error
