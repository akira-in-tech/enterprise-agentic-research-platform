"""add source type and paper metadata

Revision ID: a3f7c9e21d64
Revises: d18e4f6a9b02
Create Date: 2026-08-07 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3f7c9e21d64"
down_revision: str | Sequence[str] | None = "d18e4f6a9b02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add academic-source metadata columns to research_sources."""

    op.add_column(
        "research_sources",
        sa.Column(
            "source_type",
            sa.String(length=10),
            nullable=False,
            server_default="web",
        ),
    )
    op.add_column(
        "research_sources",
        sa.Column(
            "authors",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "research_sources",
        sa.Column("year", sa.Integer(), nullable=True),
    )
    op.add_column(
        "research_sources",
        sa.Column("venue", sa.String(length=300), nullable=True),
    )


def downgrade() -> None:
    """Remove academic-source metadata columns from research_sources."""

    op.drop_column("research_sources", "venue")
    op.drop_column("research_sources", "year")
    op.drop_column("research_sources", "authors")
    op.drop_column("research_sources", "source_type")
