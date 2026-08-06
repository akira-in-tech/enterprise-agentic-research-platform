"""add vector document identity

Revision ID: e2187a94b6c1
Revises: c4a81f9d2e73
Create Date: 2026-08-05 13:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e2187a94b6c1"
down_revision: str | Sequence[str] | None = "c4a81f9d2e73"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Link durable document metadata to deterministic Milvus identities."""

    op.add_column(
        "knowledge_documents",
        sa.Column("vector_document_id", sa.String(length=20), nullable=True),
    )
    op.create_unique_constraint(
        op.f("uq_knowledge_documents_tenant_vector_document_id"),
        "knowledge_documents",
        ["tenant_id", "vector_document_id"],
    )
    op.drop_constraint(
        op.f("ck_knowledge_documents_indexed_state_valid"),
        "knowledge_documents",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_knowledge_documents_indexed_state_valid"),
        "knowledge_documents",
        "(status = 'ready' AND indexed_at IS NOT NULL "
        "AND vector_document_id IS NOT NULL) "
        "OR (status <> 'ready' AND indexed_at IS NULL)",
    )


def downgrade() -> None:
    """Remove deterministic Milvus document identities."""

    op.drop_constraint(
        op.f("ck_knowledge_documents_indexed_state_valid"),
        "knowledge_documents",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_knowledge_documents_indexed_state_valid"),
        "knowledge_documents",
        "(status = 'ready' AND indexed_at IS NOT NULL) "
        "OR (status <> 'ready' AND indexed_at IS NULL)",
    )
    op.drop_constraint(
        op.f("uq_knowledge_documents_tenant_vector_document_id"),
        "knowledge_documents",
        type_="unique",
    )
    op.drop_column("knowledge_documents", "vector_document_id")
