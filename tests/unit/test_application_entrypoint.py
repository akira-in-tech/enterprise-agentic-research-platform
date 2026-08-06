import sys
from unittest.mock import Mock

import pytest

from app import entrypoint


def test_build_managed_database_url_encodes_credentials() -> None:
    result = entrypoint.build_managed_database_url(
        {
            "POSTGRES_HOST": "database.internal",
            "POSTGRES_DB": "research_platform",
            "POSTGRES_USER": "research_admin",
            "POSTGRES_PASSWORD": "secret/@: value",
        }
    )

    assert result == (
        "postgresql+asyncpg://research_admin:secret%2F%40%3A value@"
        "database.internal:5432/research_platform?ssl=require"
    )


def test_build_managed_redis_url_encodes_token() -> None:
    result = entrypoint.build_managed_redis_url(
        {
            "REDIS_HOST": "cache.internal",
            "REDIS_AUTH_TOKEN": "secret/@: value",
        }
    )

    assert result == "rediss://:secret%2F%40%3A%20value@cache.internal:6379/0"


def test_runtime_environment_preserves_explicit_urls() -> None:
    environ = {
        "DATABASE_URL": "postgresql+asyncpg://explicit/database",
        "REDIS_URL": "redis://explicit/0",
        "POSTGRES_HOST": "ignored",
        "REDIS_HOST": "ignored",
    }

    entrypoint.configure_runtime_environment(environ)

    assert environ["DATABASE_URL"] == "postgresql+asyncpg://explicit/database"
    assert environ["REDIS_URL"] == "redis://explicit/0"


def test_runtime_environment_rejects_partial_managed_configuration() -> None:
    with pytest.raises(
        RuntimeError,
        match="Incomplete PostgreSQL configuration",
    ):
        entrypoint.configure_runtime_environment(
            {
                "POSTGRES_HOST": "database.internal",
            }
        )


def test_main_runs_migrations_before_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure = Mock()
    run = Mock()
    execv = Mock(side_effect=SystemExit)
    monkeypatch.setattr(entrypoint, "configure_runtime_environment", configure)
    monkeypatch.setattr("app.entrypoint.subprocess.run", run)
    monkeypatch.setattr("app.entrypoint.os.execv", execv)

    with pytest.raises(SystemExit):
        entrypoint.main()

    configure.assert_called_once_with()
    run.assert_called_once_with(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
    )
    execv.assert_called_once()
