from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_step import ResearchAgentStep


class ResearchAgentStepRepository:
    """Record and retrieve one research run's per-agent step trace."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        sequence: int,
        agent_role: str,
        status: str,
        summary: str | None = None,
    ) -> ResearchAgentStep:
        """Append one step without overwriting prior history."""

        if sequence < 0:
            raise ValueError("sequence must not be negative.")

        normalized_role = agent_role.strip()
        normalized_status = status.strip()

        if not normalized_role:
            raise ValueError("agent_role must not be empty.")

        if normalized_status not in {"started", "completed", "failed"}:
            raise ValueError("status must be started, completed, or failed.")

        step = ResearchAgentStep(
            tenant_id=tenant_id,
            research_run_id=research_run_id,
            sequence=sequence,
            agent_role=normalized_role,
            status=normalized_status,
            summary=summary.strip() if summary and summary.strip() else None,
        )
        self._session.add(step)
        await self._session.flush()
        return step

    async def list_for_run(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> list[ResearchAgentStep]:
        """Return one run's steps in recorded order."""

        result = await self._session.scalars(
            select(ResearchAgentStep)
            .where(
                ResearchAgentStep.tenant_id == tenant_id,
                ResearchAgentStep.research_run_id == research_run_id,
            )
            .order_by(ResearchAgentStep.sequence)
        )
        return list(result)
