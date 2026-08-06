"""add knowledge documents

Revision ID: c4a81f9d2e73
Revises: 9bd72c6f8a10
Create Date: 2026-08-05 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4a81f9d2e73"
down_revision: str | Sequence[str] | None = "9bd72c6f8a10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create tenant-scoped private-knowledge document metadata."""

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "byte_size > 0",
            name=op.f("ck_knowledge_documents_byte_size_positive"),
        ),
        sa.CheckConstraint(
            "length(content_sha256) = 64 AND content_sha256 = lower(content_sha256)",
            name=op.f("ck_knowledge_documents_content_sha256_valid"),
        ),
        sa.CheckConstraint(
            "(status = 'failed' AND error_message IS NOT NULL "
            "AND length(trim(error_message)) > 0) "
            "OR (status <> 'failed' AND error_message IS NULL)",
            name=op.f("ck_knowledge_documents_error_state_valid"),
        ),
        sa.CheckConstraint(
            "length(trim(filename)) > 0",
            name=op.f("ck_knowledge_documents_filename_not_blank"),
        ),
        sa.CheckConstraint(
            "(status = 'ready' AND indexed_at IS NOT NULL) "
            "OR (status <> 'ready' AND indexed_at IS NULL)",
            name=op.f("ck_knowledge_documents_indexed_state_valid"),
        ),
        sa.CheckConstraint(
            "media_type IN ('text/plain', 'text/markdown', 'application/pdf')",
            name=op.f("ck_knowledge_documents_media_type_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'indexing', 'ready', 'failed', 'deleting')",
            name=op.f("ck_knowledge_documents_status_valid"),
        ),
        sa.CheckConstraint(
            "length(trim(storage_key)) > 0",
            name=op.f("ck_knowledge_documents_storage_key_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "uploaded_by_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_knowledge_documents_tenant_user",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_knowledge_documents_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_documents")),
        sa.UniqueConstraint(
            "tenant_id",
            "content_sha256",
            name="uq_knowledge_documents_tenant_content_sha256",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_knowledge_documents_tenant_id_id",
        ),
    )
    op.create_index(
        "ix_knowledge_documents_tenant_created_at",
        "knowledge_documents",
        ["tenant_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_documents_tenant_status",
        "knowledge_documents",
        ["tenant_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    """Drop tenant-scoped private-knowledge document metadata."""

    op.drop_index(
        "ix_knowledge_documents_tenant_status",
        table_name="knowledge_documents",
    )
    op.drop_index(
        "ix_knowledge_documents_tenant_created_at",
        table_name="knowledge_documents",
    )
    op.drop_table("knowledge_documents")
