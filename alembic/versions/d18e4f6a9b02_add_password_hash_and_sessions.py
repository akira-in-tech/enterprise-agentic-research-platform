"""add password hash and sessions

Revision ID: d18e4f6a9b02
Revises: c5969663fa4e
Create Date: 2026-08-05 22:10:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d18e4f6a9b02"
down_revision: str | Sequence[str] | None = "c5969663fa4e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add hashed passwords, a global email uniqueness rule, and durable sessions."""

    op.add_column(
        "users",
        sa.Column("password_hash", sa.String(length=255), nullable=False),
    )
    op.create_unique_constraint(
        op.f("uq_users_email"),
        "users",
        ["email"],
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_sessions_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint(
            "token_hash",
            name=op.f("uq_sessions_token_hash"),
        ),
    )


def downgrade() -> None:
    """Drop sessions and revert password/email uniqueness changes."""

    op.drop_table("sessions")
    op.drop_constraint(
        op.f("uq_users_email"),
        "users",
        type_="unique",
    )
    op.drop_column("users", "password_hash")
