"""add report human review flag

Revision ID: ddb663dddcad
Revises: a3f7c9e21d64
Create Date: 2026-08-10 09:45:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ddb663dddcad"
down_revision: str | Sequence[str] | None = "a3f7c9e21d64"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist the reflection agent's human-review flag on durable reports.

    The flag was already computed for every run but only ever reached the
    legacy synchronous research-run response -- the durable report row (the
    one every async job-based run and the GET .../report endpoint actually
    use) silently dropped it.
    """

    op.add_column(
        "research_reports",
        sa.Column(
            "human_review_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "research_reports",
        sa.Column("human_review_reason", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    """Drop the human-review columns."""

    op.drop_column("research_reports", "human_review_reason")
    op.drop_column("research_reports", "human_review_required")
