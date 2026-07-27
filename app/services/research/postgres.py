from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import ResearchRunRepository
from app.services.llm.factory import CanonicalLLMProvider


class TransactionalSessionFactory(Protocol):
    """Create a session with an automatically managed transaction."""

    def begin(
        self,
    ) -> AbstractAsyncContextManager[AsyncSession]:
        """Open one short database transaction."""


RepositoryFactory = Callable[
    [AsyncSession],
    ResearchRunRepository,
]


class PostgresResearchRunStore:
    """Persist research lifecycle changes using short transactions."""

    def __init__(
        self,
        session_factory: TransactionalSessionFactory,
        repository_factory: RepositoryFactory = ResearchRunRepository,
    ) -> None:
        self._session_factory = session_factory
        self._repository_factory = repository_factory

    async def create_queued(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: CanonicalLLMProvider,
        requested_by_user_id: UUID | None,
    ) -> UUID:
        """Create and commit one queued research run."""

        async with self._session_factory.begin() as session:
            repository = self._repository_factory(
                session,
            )
            research_run = await repository.create(
                tenant_id=tenant_id,
                requested_by_user_id=requested_by_user_id,
                query=query,
                llm_provider=llm_provider,
            )

            return research_run.id

    async def mark_running(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> None:
        """Commit the transition from queued to running."""

        async with self._session_factory.begin() as session:
            repository = self._repository_factory(
                session,
            )
            await repository.mark_running(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
            )

    async def mark_completed(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> None:
        """Commit the transition from running to completed."""

        async with self._session_factory.begin() as session:
            repository = self._repository_factory(
                session,
            )
            await repository.mark_completed(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
            )

    async def mark_failed(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        error_message: str,
    ) -> None:
        """Commit the transition from an active state to failed."""

        async with self._session_factory.begin() as session:
            repository = self._repository_factory(
                session,
            )
            await repository.mark_failed(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
                error_message=error_message,
            )
