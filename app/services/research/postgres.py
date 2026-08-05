from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager
from typing import Protocol, cast
from uuid import UUID

from pydantic_core import to_jsonable_python
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ResearchCheckpoint, ResearchWorkerLease
from app.db.repositories import (
    ResearchDurabilityRepository,
    ResearchReportRepository,
    ResearchRunRepository,
)
from app.services.llm.factory import CanonicalLLMProvider
from app.services.research.durability import (
    RecoverableResearchRunRecord,
    ResearchCheckpointRecord,
    ResearchWorkerLeaseRecord,
)
from app.workflow.state import ResearchState


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
ReportRepositoryFactory = Callable[[AsyncSession], ResearchReportRepository]
DurabilityRepositoryFactory = Callable[
    [AsyncSession],
    ResearchDurabilityRepository,
]


class PostgresResearchRunStore:
    """Persist research lifecycle changes using short transactions."""

    def __init__(
        self,
        session_factory: TransactionalSessionFactory,
        repository_factory: RepositoryFactory = ResearchRunRepository,
        report_repository_factory: ReportRepositoryFactory = ResearchReportRepository,
    ) -> None:
        self._session_factory = session_factory
        self._repository_factory = repository_factory
        self._report_repository_factory = report_repository_factory

    async def create_queued(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: CanonicalLLMProvider,
        requested_by_user_id: UUID | None,
        research_run_id: UUID | None = None,
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
                research_run_id=research_run_id,
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
        result: ResearchState | None = None,
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

            if result is not None:
                report_repository = self._report_repository_factory(session)
                await report_repository.create_from_state(
                    tenant_id=tenant_id,
                    research_run_id=research_run_id,
                    state=result,
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


class PostgresResearchDurabilityStore:
    """Run each durability operation in one short database transaction."""

    def __init__(
        self,
        session_factory: TransactionalSessionFactory,
        repository_factory: DurabilityRepositoryFactory = ResearchDurabilityRepository,
    ) -> None:
        self._session_factory = session_factory
        self._repository_factory = repository_factory

    async def claim_lease(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        worker_id: str,
        ttl_seconds: int,
    ) -> ResearchWorkerLeaseRecord | None:
        async with self._session_factory.begin() as session:
            lease = await self._repository_factory(session).claim_lease(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
                worker_id=worker_id,
                ttl_seconds=ttl_seconds,
            )
            return self._lease_record(lease)

    async def renew_lease(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        worker_id: str,
        lease_token: UUID,
        ttl_seconds: int,
    ) -> ResearchWorkerLeaseRecord | None:
        async with self._session_factory.begin() as session:
            lease = await self._repository_factory(session).renew_lease(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
                worker_id=worker_id,
                lease_token=lease_token,
                ttl_seconds=ttl_seconds,
            )
            return self._lease_record(lease)

    async def release_lease(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        worker_id: str,
        lease_token: UUID,
    ) -> bool:
        async with self._session_factory.begin() as session:
            return await self._repository_factory(session).release_lease(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
                worker_id=worker_id,
                lease_token=lease_token,
            )

    async def append_checkpoint(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        sequence: int,
        node_name: str,
        state: Mapping[str, object],
    ) -> ResearchCheckpointRecord:
        normalized_state = cast(
            dict[str, object],
            to_jsonable_python(dict(state), fallback=str),
        )
        async with self._session_factory.begin() as session:
            checkpoint = await self._repository_factory(session).append_checkpoint(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
                sequence=sequence,
                node_name=node_name,
                state=normalized_state,
            )
            return self._checkpoint_record(checkpoint)

    async def get_latest_checkpoint(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> ResearchCheckpointRecord | None:
        async with self._session_factory.begin() as session:
            checkpoint = await self._repository_factory(session).get_latest_checkpoint(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
            )
            if checkpoint is None:
                return None
            return self._checkpoint_record(checkpoint)

    async def append_audit_event(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        event_type: str,
        actor_type: str,
        actor_id: str | None = None,
        details: Mapping[str, object] | None = None,
    ) -> None:
        normalized_details = cast(
            dict[str, object],
            to_jsonable_python(dict(details or {}), fallback=str),
        )
        async with self._session_factory.begin() as session:
            await self._repository_factory(session).append_audit_event(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
                event_type=event_type,
                actor_type=actor_type,
                actor_id=actor_id,
                details=normalized_details,
            )

    async def list_recoverable_runs(
        self,
        *,
        limit: int = 100,
    ) -> list[RecoverableResearchRunRecord]:
        async with self._session_factory.begin() as session:
            runs = await self._repository_factory(session).list_recoverable_runs(
                limit=limit,
            )
            return [
                RecoverableResearchRunRecord(
                    research_run_id=run.id,
                    tenant_id=run.tenant_id,
                    requested_by_user_id=run.requested_by_user_id,
                    query=run.query,
                    llm_provider=run.llm_provider,
                    status=run.status,
                )
                for run in runs
            ]

    @staticmethod
    def _lease_record(
        lease: ResearchWorkerLease | None,
    ) -> ResearchWorkerLeaseRecord | None:
        if lease is None:
            return None
        return ResearchWorkerLeaseRecord(
            tenant_id=lease.tenant_id,
            research_run_id=lease.research_run_id,
            worker_id=lease.worker_id,
            lease_token=lease.lease_token,
            attempt=lease.attempt,
            acquired_at=lease.acquired_at,
            heartbeat_at=lease.heartbeat_at,
            expires_at=lease.expires_at,
        )

    @staticmethod
    def _checkpoint_record(checkpoint: ResearchCheckpoint) -> ResearchCheckpointRecord:
        return ResearchCheckpointRecord(
            sequence=checkpoint.sequence,
            node_name=checkpoint.node_name,
            state=dict(checkpoint.state),
            created_at=checkpoint.created_at,
        )
