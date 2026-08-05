from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ResearchCheckpoint(Base):
    """Persist one resumable workflow-state snapshot."""

    __tablename__ = "research_checkpoints"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "research_run_id"],
            ["research_runs.tenant_id", "research_runs.id"],
            name="fk_research_checkpoints_tenant_run",
            ondelete="CASCADE",
        ),
        CheckConstraint("sequence >= 0", name="sequence_non_negative"),
        CheckConstraint("length(trim(node_name)) > 0", name="node_name_not_blank"),
        UniqueConstraint(
            "tenant_id",
            "research_run_id",
            "sequence",
            name="uq_research_checkpoints_tenant_run_sequence",
        ),
        Index(
            "ix_research_checkpoints_tenant_run_created_at",
            "tenant_id",
            "research_run_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    research_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    node_name: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ResearchAuditEvent(Base):
    """Record an append-only operational event for one research run."""

    __tablename__ = "research_audit_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "research_run_id"],
            ["research_runs.tenant_id", "research_runs.id"],
            name="fk_research_audit_events_tenant_run",
            ondelete="CASCADE",
        ),
        CheckConstraint("length(trim(event_type)) > 0", name="event_type_not_blank"),
        CheckConstraint(
            "actor_type IN ('user', 'worker', 'system')",
            name="actor_type_valid",
        ),
        Index(
            "ix_research_audit_events_tenant_run_created_at",
            "tenant_id",
            "research_run_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    research_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    details: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ResearchWorkerLease(Base):
    """Represent exclusive, expiring worker ownership of one queued run."""

    __tablename__ = "research_worker_leases"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "research_run_id"],
            ["research_runs.tenant_id", "research_runs.id"],
            name="fk_research_worker_leases_tenant_run",
            ondelete="CASCADE",
        ),
        CheckConstraint("length(trim(worker_id)) > 0", name="worker_id_not_blank"),
        CheckConstraint("attempt >= 1", name="attempt_positive"),
        CheckConstraint("expires_at > heartbeat_at", name="expiry_after_heartbeat"),
        UniqueConstraint("lease_token", name="uq_research_worker_leases_lease_token"),
        Index("ix_research_worker_leases_expires_at", "expires_at"),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    research_run_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    worker_id: Mapped[str] = mapped_column(String(200), nullable=False)
    lease_token: Mapped[UUID] = mapped_column(Uuid, nullable=False, default=uuid4)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
