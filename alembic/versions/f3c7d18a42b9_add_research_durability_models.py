"""add research durability models

Revision ID: f3c7d18a42b9
Revises: e2187a94b6c1
Create Date: 2026-08-05 17:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f3c7d18a42b9"
down_revision: str | Sequence[str] | None = "e2187a94b6c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create checkpoints, audit events, and worker leases."""

    op.create_table(
        "research_checkpoints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("research_run_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("node_name", sa.String(length=100), nullable=False),
        sa.Column("state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(node_name)) > 0", name=op.f("ck_research_checkpoints_node_name_not_blank")
        ),
        sa.CheckConstraint(
            "sequence >= 0", name=op.f("ck_research_checkpoints_sequence_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "research_run_id"],
            ["research_runs.tenant_id", "research_runs.id"],
            name=op.f("fk_research_checkpoints_tenant_run"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_research_checkpoints")),
        sa.UniqueConstraint(
            "tenant_id",
            "research_run_id",
            "sequence",
            name=op.f("uq_research_checkpoints_tenant_run_sequence"),
        ),
    )
    op.create_index(
        "ix_research_checkpoints_tenant_run_created_at",
        "research_checkpoints",
        ["tenant_id", "research_run_id", "created_at"],
    )

    op.create_table(
        "research_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("research_run_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("actor_type", sa.String(length=20), nullable=False),
        sa.Column("actor_id", sa.String(length=200), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "actor_type IN ('user', 'worker', 'system')",
            name=op.f("ck_research_audit_events_actor_type_valid"),
        ),
        sa.CheckConstraint(
            "length(trim(event_type)) > 0",
            name=op.f("ck_research_audit_events_event_type_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "research_run_id"],
            ["research_runs.tenant_id", "research_runs.id"],
            name=op.f("fk_research_audit_events_tenant_run"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_research_audit_events")),
    )
    op.create_index(
        "ix_research_audit_events_tenant_run_created_at",
        "research_audit_events",
        ["tenant_id", "research_run_id", "created_at"],
    )

    op.create_table(
        "research_worker_leases",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("research_run_id", sa.Uuid(), nullable=False),
        sa.Column("worker_id", sa.String(length=200), nullable=False),
        sa.Column("lease_token", sa.Uuid(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column(
            "acquired_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempt >= 1", name=op.f("ck_research_worker_leases_attempt_positive")),
        sa.CheckConstraint(
            "expires_at > heartbeat_at",
            name=op.f("ck_research_worker_leases_expiry_after_heartbeat"),
        ),
        sa.CheckConstraint(
            "length(trim(worker_id)) > 0",
            name=op.f("ck_research_worker_leases_worker_id_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "research_run_id"],
            ["research_runs.tenant_id", "research_runs.id"],
            name=op.f("fk_research_worker_leases_tenant_run"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id", "research_run_id", name=op.f("pk_research_worker_leases")
        ),
        sa.UniqueConstraint("lease_token", name=op.f("uq_research_worker_leases_lease_token")),
    )
    op.create_index(
        "ix_research_worker_leases_expires_at",
        "research_worker_leases",
        ["expires_at"],
    )


def downgrade() -> None:
    """Remove worker leases, audit events, and checkpoints."""

    op.drop_index("ix_research_worker_leases_expires_at", table_name="research_worker_leases")
    op.drop_table("research_worker_leases")
    op.drop_index(
        "ix_research_audit_events_tenant_run_created_at",
        table_name="research_audit_events",
    )
    op.drop_table("research_audit_events")
    op.drop_index(
        "ix_research_checkpoints_tenant_run_created_at",
        table_name="research_checkpoints",
    )
    op.drop_table("research_checkpoints")
