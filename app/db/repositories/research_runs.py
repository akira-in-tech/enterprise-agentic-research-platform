from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ResearchRun

SUPPORTED_LLM_PROVIDERS = frozenset(
    {
        "anthropic",
        "ollama",
    }
)


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
