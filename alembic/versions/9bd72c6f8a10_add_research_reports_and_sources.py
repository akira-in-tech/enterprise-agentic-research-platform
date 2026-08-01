"""add research reports and sources

Revision ID: 9bd72c6f8a10
Revises: 0eea26dcdef5
Create Date: 2026-08-01 06:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9bd72c6f8a10"
down_revision: str | Sequence[str] | None = "0eea26dcdef5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create durable report and evidence-source tables."""

    op.create_unique_constraint(
        "uq_research_runs_tenant_id_id",
        "research_runs",
        ["tenant_id", "id"],
    )
    op.create_table(
        "research_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("research_run_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("workflow_status", sa.String(length=100), nullable=False),
        sa.Column("citation_valid", sa.Boolean(), nullable=False),
        sa.Column("citation_coverage", sa.Float(), nullable=False),
        sa.Column("reflection_status", sa.String(length=20), nullable=False),
        sa.Column("reflection_reasons", sa.JSON(), nullable=False),
        sa.Column("reflection_attempts", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "research_run_id"],
            ["research_runs.tenant_id", "research_runs.id"],
            name="fk_research_reports_tenant_run",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_research_reports")),
        sa.UniqueConstraint("research_run_id", name="uq_research_reports_research_run_id"),
    )
    op.create_index(
        "ix_research_reports_tenant_created_at",
        "research_reports",
        ["tenant_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "research_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("research_run_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.String(length=40), nullable=False),
        sa.Column("origin", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("locator", sa.String(length=2048), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("relevance", sa.Float(), nullable=False),
        sa.Column("content_quality", sa.Float(), nullable=False),
        sa.Column("traceability", sa.Float(), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("cited", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["research_reports.id"],
            name="fk_research_sources_report_id_research_reports",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_research_sources")),
        sa.UniqueConstraint("report_id", "source_id", name="uq_research_sources_report_source"),
    )
    op.create_index(
        "ix_research_sources_tenant_run",
        "research_sources",
        ["tenant_id", "research_run_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop durable report and evidence-source tables."""

    op.drop_index("ix_research_sources_tenant_run", table_name="research_sources")
    op.drop_table("research_sources")
    op.drop_index("ix_research_reports_tenant_created_at", table_name="research_reports")
    op.drop_table("research_reports")
    op.drop_constraint(
        "uq_research_runs_tenant_id_id",
        "research_runs",
        type_="unique",
    )
