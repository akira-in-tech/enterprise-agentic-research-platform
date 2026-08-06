"""add research cancellation status

Revision ID: a71d64c0b3e2
Revises: f3c7d18a42b9
Create Date: 2026-08-05 21:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a71d64c0b3e2"
down_revision: str | Sequence[str] | None = "f3c7d18a42b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Allow active research runs to reach a durable cancelled state."""

    op.drop_constraint(
        op.f("ck_research_runs_status_valid"),
        "research_runs",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_research_runs_status_valid"),
        "research_runs",
        "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
    )


def downgrade() -> None:
    """Restore the status set after removing cancelled rows."""

    op.execute(
        sa.text(
            """
            UPDATE research_runs
            SET status = 'failed',
                completed_at = COALESCE(completed_at, now()),
                error_message = COALESCE(
                    error_message,
                    'Cancelled before schema downgrade.'
                )
            WHERE status = 'cancelled'
            """
        )
    )
    op.drop_constraint(
        op.f("ck_research_runs_status_valid"),
        "research_runs",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_research_runs_status_valid"),
        "research_runs",
        "status IN ('queued', 'running', 'completed', 'failed')",
    )
