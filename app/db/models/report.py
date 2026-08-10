from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ResearchReport(Base):
    """Represent one durable evidence-backed report."""

    __tablename__ = "research_reports"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "research_run_id"],
            ["research_runs.tenant_id", "research_runs.id"],
            name="fk_research_reports_tenant_run",
            ondelete="CASCADE",
        ),
        UniqueConstraint("research_run_id", name="uq_research_reports_research_run_id"),
        Index("ix_research_reports_tenant_created_at", "tenant_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    research_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    workflow_status: Mapped[str] = mapped_column(String(100), nullable=False)
    citation_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    citation_coverage: Mapped[float] = mapped_column(Float, nullable=False)
    reflection_status: Mapped[str] = mapped_column(String(20), nullable=False)
    reflection_reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    reflection_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    human_review_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    human_review_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ResearchSource(Base):
    """Represent one durable evidence source attached to a report."""

    __tablename__ = "research_sources"
    __table_args__ = (
        UniqueConstraint("report_id", "source_id", name="uq_research_sources_report_source"),
        Index("ix_research_sources_tenant_run", "tenant_id", "research_run_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    report_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "research_reports.id",
            name="fk_research_sources_report_id_research_reports",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    research_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    source_id: Mapped[str] = mapped_column(String(40), nullable=False)
    origin: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    locator: Mapped[str] = mapped_column(String(2048), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    relevance: Mapped[float] = mapped_column(Float, nullable=False)
    content_quality: Mapped[float] = mapped_column(Float, nullable=False)
    traceability: Mapped[float] = mapped_column(Float, nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    cited: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source_type: Mapped[str] = mapped_column(String(10), nullable=False, server_default="web")
    authors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(300), nullable=True)
