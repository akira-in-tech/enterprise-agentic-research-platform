"""add report evidence conflicts

Revision ID: 56b79217d185
Revises: ddb663dddcad
Create Date: 2026-08-10 10:20:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "56b79217d185"
down_revision: str | Sequence[str] | None = "ddb663dddcad"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist the Evidence Judge's flagged source conflicts on durable reports.

    Like human_review_required before it, evidence_conflicts was computed by
    the EvidenceJudgeAgent and stored in the LangGraph run state, but nothing
    downstream ever read it -- not the Analyst, not the persisted report row,
    not the API response. It was fully computed and then discarded.
    """

    op.add_column(
        "research_reports",
        sa.Column(
            "evidence_conflicts",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    """Drop the evidence_conflicts column."""

    op.drop_column("research_reports", "evidence_conflicts")
