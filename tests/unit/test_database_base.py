from sqlalchemy import MetaData

from app.db.base import Base
from app.db.models import KnowledgeDocument, ResearchRun, Tenant, User, metadata


def test_database_base_exposes_registered_metadata() -> None:
    assert isinstance(
        metadata,
        MetaData,
    )
    assert metadata is Base.metadata
    assert set(metadata.tables) == {
        "knowledge_documents",
        "research_agent_steps",
        "research_audit_events",
        "research_checkpoints",
        "research_reports",
        "research_runs",
        "research_sources",
        "research_worker_leases",
        "tenants",
        "users",
    }
    assert Tenant.__table__ is metadata.tables["tenants"]
    assert User.__table__ is metadata.tables["users"]
    assert ResearchRun.__table__ is metadata.tables["research_runs"]
    assert KnowledgeDocument.__table__ is metadata.tables["knowledge_documents"]
