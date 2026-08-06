from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ResearchAgentStep(Base):
    """Record one durable step of the canonical eight-agent workflow."""

    __tablename__ = "research_agent_steps"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "research_run_id"],
            ["research_runs.tenant_id", "research_runs.id"],
            name="fk_research_agent_steps_tenant_run",
            ondelete="CASCADE",
        ),
        CheckConstraint("sequence >= 0", name="sequence_non_negative"),
        CheckConstraint(
            "agent_role IN ('intent_router', 'planner', 'web_scout', 'local_scout', "
            "'evidence_judge', 'analyst', 'reflect', 'writer', 'direct_answer')",
            name="agent_role_valid",
        ),
        CheckConstraint(
            "status IN ('started', 'completed', 'failed')",
            name="status_valid",
        ),
        UniqueConstraint(
            "tenant_id",
            "research_run_id",
            "sequence",
            name="uq_research_agent_steps_tenant_run_sequence",
        ),
        Index(
            "ix_research_agent_steps_tenant_run_created_at",
            "tenant_id",
            "research_run_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    research_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_role: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
