from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ResearchAuditEvent,
    ResearchCheckpoint,
    ResearchRun,
    ResearchWorkerLease,
)


class ResearchDurabilityRepository:
    """Persist checkpoints, audit events, and atomic worker leases."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append_checkpoint(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        sequence: int,
        node_name: str,
        state: Mapping[str, object],
    ) -> ResearchCheckpoint:
        """Append one immutable workflow checkpoint."""

        normalized_node = node_name.strip()
        if sequence < 0:
            raise ValueError("checkpoint sequence must not be negative.")
        if not normalized_node:
            raise ValueError("checkpoint node_name must not be empty.")

        checkpoint = ResearchCheckpoint(
            tenant_id=tenant_id,
            research_run_id=research_run_id,
            sequence=sequence,
            node_name=normalized_node,
            state=dict(state),
        )
        self._session.add(checkpoint)
        await self._session.flush()
        return checkpoint

    async def get_latest_checkpoint(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> ResearchCheckpoint | None:
        """Return the latest checkpoint within one tenant-scoped run."""

        statement = (
            select(ResearchCheckpoint)
            .where(
                ResearchCheckpoint.tenant_id == tenant_id,
                ResearchCheckpoint.research_run_id == research_run_id,
            )
            .order_by(ResearchCheckpoint.sequence.desc())
            .limit(1)
        )
        return cast(ResearchCheckpoint | None, await self._session.scalar(statement))

    async def append_audit_event(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        event_type: str,
        actor_type: str,
        actor_id: str | None = None,
        details: Mapping[str, object] | None = None,
    ) -> ResearchAuditEvent:
        """Append one operational event without overwriting prior history."""

        normalized_event = event_type.strip()
        normalized_actor = actor_type.strip().lower()
        if not normalized_event:
            raise ValueError("audit event_type must not be empty.")
        if normalized_actor not in {"user", "worker", "system"}:
            raise ValueError("audit actor_type must be user, worker, or system.")

        event = ResearchAuditEvent(
            tenant_id=tenant_id,
            research_run_id=research_run_id,
            event_type=normalized_event,
            actor_type=normalized_actor,
            actor_id=actor_id.strip() if actor_id and actor_id.strip() else None,
            details=dict(details or {}),
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def list_audit_events(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        limit: int = 100,
    ) -> list[ResearchAuditEvent]:
        """Return a bounded chronological audit trail."""

        if not 1 <= limit <= 500:
            raise ValueError("audit limit must be between 1 and 500.")
        statement = (
            select(ResearchAuditEvent)
            .where(
                ResearchAuditEvent.tenant_id == tenant_id,
                ResearchAuditEvent.research_run_id == research_run_id,
            )
            .order_by(ResearchAuditEvent.created_at.asc(), ResearchAuditEvent.id.asc())
            .limit(limit)
        )
        return list(await self._session.scalars(statement))

    async def claim_lease(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        worker_id: str,
        ttl_seconds: int,
        now: datetime | None = None,
        lease_token: UUID | None = None,
    ) -> ResearchWorkerLease | None:
        """Atomically create a lease or replace only an expired lease."""

        normalized_worker = worker_id.strip()
        if not normalized_worker:
            raise ValueError("worker_id must not be empty.")
        if not 1 <= ttl_seconds <= 3600:
            raise ValueError("lease ttl_seconds must be between 1 and 3600.")

        claimed_at = now or datetime.now(UTC)
        expires_at = claimed_at + timedelta(seconds=ttl_seconds)
        token = lease_token or uuid4()
        statement = (
            insert(ResearchWorkerLease)
            .values(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
                worker_id=normalized_worker,
                lease_token=token,
                attempt=1,
                acquired_at=claimed_at,
                heartbeat_at=claimed_at,
                expires_at=expires_at,
            )
            .on_conflict_do_update(
                index_elements=[
                    ResearchWorkerLease.tenant_id,
                    ResearchWorkerLease.research_run_id,
                ],
                set_={
                    "worker_id": normalized_worker,
                    "lease_token": token,
                    "attempt": ResearchWorkerLease.attempt + 1,
                    "acquired_at": claimed_at,
                    "heartbeat_at": claimed_at,
                    "expires_at": expires_at,
                },
                where=ResearchWorkerLease.expires_at <= claimed_at,
            )
            .returning(ResearchWorkerLease)
        )
        return cast(ResearchWorkerLease | None, await self._session.scalar(statement))

    async def renew_lease(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        worker_id: str,
        lease_token: UUID,
        ttl_seconds: int,
        now: datetime | None = None,
    ) -> ResearchWorkerLease | None:
        """Extend one unexpired lease only for its current token owner."""

        heartbeat_at = now or datetime.now(UTC)
        if not 1 <= ttl_seconds <= 3600:
            raise ValueError("lease ttl_seconds must be between 1 and 3600.")
        statement = (
            update(ResearchWorkerLease)
            .where(
                ResearchWorkerLease.tenant_id == tenant_id,
                ResearchWorkerLease.research_run_id == research_run_id,
                ResearchWorkerLease.worker_id == worker_id.strip(),
                ResearchWorkerLease.lease_token == lease_token,
                ResearchWorkerLease.expires_at > heartbeat_at,
            )
            .values(
                heartbeat_at=heartbeat_at,
                expires_at=heartbeat_at + timedelta(seconds=ttl_seconds),
            )
            .returning(ResearchWorkerLease)
        )
        return cast(ResearchWorkerLease | None, await self._session.scalar(statement))

    async def release_lease(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        worker_id: str,
        lease_token: UUID,
    ) -> bool:
        """Delete one lease only when both worker identity and token match."""

        statement = (
            delete(ResearchWorkerLease)
            .where(
                ResearchWorkerLease.tenant_id == tenant_id,
                ResearchWorkerLease.research_run_id == research_run_id,
                ResearchWorkerLease.worker_id == worker_id.strip(),
                ResearchWorkerLease.lease_token == lease_token,
            )
            .returning(ResearchWorkerLease.research_run_id)
        )
        return await self._session.scalar(statement) is not None

    async def list_recoverable_runs(
        self,
        *,
        limit: int = 100,
        now: datetime | None = None,
    ) -> list[ResearchRun]:
        """List queued/running runs whose lease is absent or expired."""

        if not 1 <= limit <= 500:
            raise ValueError("recoverable run limit must be between 1 and 500.")
        current_time = now or datetime.now(UTC)
        statement = (
            select(ResearchRun)
            .outerjoin(
                ResearchWorkerLease,
                (
                    (ResearchWorkerLease.tenant_id == ResearchRun.tenant_id)
                    & (ResearchWorkerLease.research_run_id == ResearchRun.id)
                ),
            )
            .where(
                ResearchRun.status.in_(("queued", "running")),
                or_(
                    ResearchWorkerLease.research_run_id.is_(None),
                    ResearchWorkerLease.expires_at <= current_time,
                ),
            )
            .order_by(ResearchRun.created_at.asc(), ResearchRun.id.asc())
            .limit(limit)
        )
        return list(await self._session.scalars(statement))
