from sqlalchemy import MetaData

from app.db.base import Base
from app.db.models import ResearchRun, Tenant, User, metadata


def test_database_base_exposes_registered_metadata() -> None:
    assert isinstance(
        metadata,
        MetaData,
    )
    assert metadata is Base.metadata
    assert set(metadata.tables) == {
        "tenants",
        "users",
        "research_runs",
    }
    assert Tenant.__table__ is metadata.tables["tenants"]
    assert User.__table__ is metadata.tables["users"]
    assert ResearchRun.__table__ is metadata.tables["research_runs"]
