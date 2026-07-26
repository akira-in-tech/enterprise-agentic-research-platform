from sqlalchemy import MetaData

from app.db.base import Base


def test_database_base_exposes_empty_metadata() -> None:
    assert isinstance(
        Base.metadata,
        MetaData,
    )
    assert list(Base.metadata.sorted_tables) == []
