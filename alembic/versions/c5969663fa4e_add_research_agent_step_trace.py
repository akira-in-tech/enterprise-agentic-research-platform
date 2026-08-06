"""add research agent step trace

Revision ID: c5969663fa4e
Revises: a71d64c0b3e2
Create Date: 2026-08-05 09:23:00.533175

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c5969663fa4e"
down_revision: str | Sequence[str] | None = "a71d64c0b3e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the per-agent-step trace for the canonical eight-agent workflow."""

    op.create_table(
        "research_agent_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("research_run_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("agent_role", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("summary", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "agent_role IN ('intent_router', 'planner', 'web_scout', 'local_scout', "
            "'evidence_judge', 'analyst', 'reflect', 'writer', 'direct_answer')",
            name=op.f("ck_research_agent_steps_agent_role_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('started', 'completed', 'failed')",
            name=op.f("ck_research_agent_steps_status_valid"),
        ),
        sa.CheckConstraint(
            "sequence >= 0", name=op.f("ck_research_agent_steps_sequence_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "research_run_id"],
            ["research_runs.tenant_id", "research_runs.id"],
            name=op.f("fk_research_agent_steps_tenant_run"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_research_agent_steps")),
        sa.UniqueConstraint(
            "tenant_id",
            "research_run_id",
            "sequence",
            name=op.f("uq_research_agent_steps_tenant_run_sequence"),
        ),
    )
    op.create_index(
        "ix_research_agent_steps_tenant_run_created_at",
        "research_agent_steps",
        ["tenant_id", "research_run_id", "created_at"],
    )


def downgrade() -> None:
    """Remove the per-agent-step trace."""

    op.drop_index(
        "ix_research_agent_steps_tenant_run_created_at",
        table_name="research_agent_steps",
    )
    op.drop_table("research_agent_steps")
