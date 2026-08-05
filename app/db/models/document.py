from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KnowledgeDocument(Base):
    """Represent one tenant-owned private-knowledge document."""

    __tablename__ = "knowledge_documents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "uploaded_by_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_knowledge_documents_tenant_user",
            ondelete="NO ACTION",
        ),
        CheckConstraint(
            "length(trim(filename)) > 0",
            name="filename_not_blank",
        ),
        CheckConstraint(
            "media_type IN ('text/plain', 'text/markdown', 'application/pdf')",
            name="media_type_valid",
        ),
        CheckConstraint(
            "byte_size > 0",
            name="byte_size_positive",
        ),
        CheckConstraint(
            "length(content_sha256) = 64 AND content_sha256 = lower(content_sha256)",
            name="content_sha256_valid",
        ),
        CheckConstraint(
            "length(trim(storage_key)) > 0",
            name="storage_key_not_blank",
        ),
        CheckConstraint(
            "status IN ('pending', 'indexing', 'ready', 'failed', 'deleting')",
            name="status_valid",
        ),
        CheckConstraint(
            "(status = 'failed' AND error_message IS NOT NULL "
            "AND length(trim(error_message)) > 0) "
            "OR (status <> 'failed' AND error_message IS NULL)",
            name="error_state_valid",
        ),
        CheckConstraint(
            "(status = 'ready' AND indexed_at IS NOT NULL) "
            "OR (status <> 'ready' AND indexed_at IS NULL)",
            name="indexed_state_valid",
        ),
        Index(
            "ix_knowledge_documents_tenant_created_at",
            "tenant_id",
            "created_at",
        ),
        Index(
            "ix_knowledge_documents_tenant_status",
            "tenant_id",
            "status",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_knowledge_documents_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "content_sha256",
            name="uq_knowledge_documents_tenant_content_sha256",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid4,
    )

    tenant_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "tenants.id",
            name="fk_knowledge_documents_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    uploaded_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        nullable=True,
    )

    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    media_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    byte_size: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    content_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    storage_key: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
