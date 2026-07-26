import asyncio

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from app.core.config import settings
from app.db.session import (
    create_database_engine,
    create_session_factory,
)


def test_create_database_engine_uses_asyncpg() -> None:
    engine = create_database_engine(
        ("postgresql+asyncpg://research_user:secret@localhost:5432/test_database"),
        echo=True,
    )

    try:
        assert engine.url.drivername == "postgresql+asyncpg"
        assert engine.url.database == "test_database"
        assert engine.echo is True
    finally:
        asyncio.run(engine.dispose())


def test_create_database_engine_uses_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "database_url",
        SecretStr("postgresql+asyncpg://research_user:secret@localhost:5432/settings_database"),
    )
    monkeypatch.setattr(
        settings,
        "database_echo",
        False,
    )

    engine = create_database_engine()

    try:
        assert engine.url.database == "settings_database"
        assert engine.echo is False
    finally:
        asyncio.run(engine.dispose())


@pytest.mark.parametrize(
    ("database_url", "expected_error"),
    [
        (
            "",
            "Database URL must not be empty",
        ),
        (
            "not-a-database-url",
            "Invalid database URL",
        ),
        (
            "postgresql://user:password@localhost/database",
            "must use the postgresql\\+asyncpg driver",
        ),
    ],
)
def test_create_database_engine_rejects_invalid_url(
    database_url: str,
    expected_error: str,
) -> None:
    with pytest.raises(
        ValueError,
        match=expected_error,
    ):
        create_database_engine(
            database_url,
        )


def test_create_session_factory_configures_async_sessions() -> None:
    engine = create_database_engine(
        "postgresql+asyncpg://research_user:secret@localhost:5432/test_database"
    )
    session_factory = create_session_factory(engine)

    async def inspect_session() -> None:
        async with session_factory() as session:
            assert isinstance(
                session,
                AsyncSession,
            )
            assert session.sync_session.autoflush is False
            assert session.sync_session.expire_on_commit is False

    try:
        asyncio.run(inspect_session())
    finally:
        asyncio.run(engine.dispose())
