from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ResearchRun

SUPPORTED_LLM_PROVIDERS = frozenset(
    {
        "anthropic",
        "ollama",
    }
)


class ResearchRunTransitionError(RuntimeError):
    """Indicate that a research run transition was rejected."""


class ResearchRunRepository:
    """Persist and query tenant-scoped research runs."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: str,
        requested_by_user_id: UUID | None = None,
    ) -> ResearchRun:
        """Create a queued run without committing its transaction."""

        normalized_query = query.strip()
        normalized_provider = llm_provider.strip().lower()

        if not normalized_query:
            raise ValueError("query must not be empty.")

        if normalized_provider not in SUPPORTED_LLM_PROVIDERS:
            raise ValueError("llm_provider must be 'anthropic' or 'ollama'.")

        research_run = ResearchRun(
            tenant_id=tenant_id,
            requested_by_user_id=requested_by_user_id,
            query=normalized_query,
            llm_provider=normalized_provider,
            status="queued",
        )

        self._session.add(research_run)
        await self._session.flush()

        return research_run

    async def get_for_tenant(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> ResearchRun | None:
        """Return a run only when it belongs to the tenant."""

        statement = select(ResearchRun).where(
            ResearchRun.id == research_run_id,
            ResearchRun.tenant_id == tenant_id,
        )

        result = await self._session.scalar(statement)

        return result

    async def list_recent_for_tenant(
        self,
        *,
        tenant_id: UUID,
        limit: int = 20,
    ) -> list[ResearchRun]:
        """Return recent runs belonging only to one tenant."""

        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100.")

        statement = (
            select(ResearchRun)
            .where(
                ResearchRun.tenant_id == tenant_id,
            )
            .order_by(
                ResearchRun.created_at.desc(),
                ResearchRun.id.desc(),
            )
            .limit(limit)
        )

        result = await self._session.scalars(statement)

        return list(result)

    async def mark_running(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> ResearchRun:
        """Atomically transition a queued run to running."""

        statement = (
            update(ResearchRun)
            .where(
                ResearchRun.id == research_run_id,
                ResearchRun.tenant_id == tenant_id,
                ResearchRun.status == "queued",
            )
            .values(
                status="running",
                started_at=func.now(),
                completed_at=None,
                error_message=None,
            )
            .returning(ResearchRun)
        )

        result = await self._session.scalar(statement)

        if result is None:
            raise ResearchRunTransitionError(
                "Research run is missing or cannot transition to running."
            )

        return result

    async def mark_completed(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> ResearchRun:
        """Atomically transition a running run to completed."""

        statement = (
            update(ResearchRun)
            .where(
                ResearchRun.id == research_run_id,
                ResearchRun.tenant_id == tenant_id,
                ResearchRun.status == "running",
            )
            .values(
                status="completed",
                completed_at=func.now(),
                error_message=None,
            )
            .returning(ResearchRun)
        )

        result = await self._session.scalar(statement)

        if result is None:
            raise ResearchRunTransitionError(
                "Research run is missing or cannot transition to completed."
            )

        return result

    async def mark_failed(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        error_message: str,
    ) -> ResearchRun:
        """Atomically transition an active run to failed."""

        normalized_error = error_message.strip()

        if not normalized_error:
            raise ValueError("error_message must not be empty.")

        if len(normalized_error) > 4_000:
            raise ValueError("error_message must not exceed 4000 characters.")

        statement = (
            update(ResearchRun)
            .where(
                ResearchRun.id == research_run_id,
                ResearchRun.tenant_id == tenant_id,
                ResearchRun.status.in_(
                    (
                        "queued",
                        "running",
                    )
                ),
            )
            .values(
                status="failed",
                completed_at=func.now(),
                error_message=normalized_error,
            )
            .returning(ResearchRun)
        )

        result = await self._session.scalar(statement)

        if result is None:
            raise ResearchRunTransitionError(
                "Research run is missing or cannot transition to failed."
            )

        return result
