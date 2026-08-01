from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
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


class ResearchRun(Base):
    """Represent one durable research workflow execution."""

    __tablename__ = "research_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            [
                "tenant_id",
                "requested_by_user_id",
            ],
            [
                "users.tenant_id",
                "users.id",
            ],
            name="fk_research_runs_tenant_user",
            ondelete="NO ACTION",
        ),
        CheckConstraint(
            "length(trim(query)) > 0",
            name="query_not_blank",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="status_valid",
        ),
        CheckConstraint(
            "llm_provider IN ('anthropic', 'ollama')",
            name="llm_provider_valid",
        ),
        CheckConstraint(
            "route IS NULL OR route IN ('direct', 'deep_research')",
            name="route_valid",
        ),
        Index(
            "ix_research_runs_tenant_created_at",
            "tenant_id",
            "created_at",
        ),
        Index(
            "ix_research_runs_tenant_status",
            "tenant_id",
            "status",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_research_runs_tenant_id_id",
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
            name="fk_research_runs_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    requested_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        nullable=True,
    )

    query: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    llm_provider: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="queued",
        server_default="queued",
    )

    route: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    route_reason: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
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

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
