from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ResearchWorkerLeaseRecord:
    """Describe one exclusive, expiring worker claim."""

    tenant_id: UUID
    research_run_id: UUID
    worker_id: str
    lease_token: UUID
    attempt: int
    acquired_at: datetime
    heartbeat_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ResearchCheckpointRecord:
    """Describe one persisted workflow checkpoint without ORM coupling."""

    sequence: int
    node_name: str
    state: dict[str, object]
    created_at: datetime


class ResearchDurabilityStore(Protocol):
    """Coordinate worker ownership, checkpoints, and audit history."""

    async def claim_lease(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        worker_id: str,
        ttl_seconds: int,
    ) -> ResearchWorkerLeaseRecord | None:
        """Atomically claim an unowned or expired run."""

    async def renew_lease(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        worker_id: str,
        lease_token: UUID,
        ttl_seconds: int,
    ) -> ResearchWorkerLeaseRecord | None:
        """Renew a lease only for its current owner token."""

    async def release_lease(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        worker_id: str,
        lease_token: UUID,
    ) -> bool:
        """Release a lease only for its current owner token."""

    async def append_checkpoint(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        sequence: int,
        node_name: str,
        state: Mapping[str, object],
    ) -> ResearchCheckpointRecord:
        """Append an immutable workflow checkpoint."""

    async def get_latest_checkpoint(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> ResearchCheckpointRecord | None:
        """Return the latest persisted checkpoint for one run."""

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
        """Append an operational audit event."""
