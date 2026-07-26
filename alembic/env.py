import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import (
    create_async_engine,
)

from alembic import context
from app.core.config import settings
from app.db.models import metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(
        config.config_file_name,
    )

target_metadata = metadata


def get_database_url() -> str:
    """Return the configured async PostgreSQL URL."""

    database_url = settings.database_url.get_secret_value().strip()

    if not database_url:
        raise RuntimeError("Database URL must not be empty.")

    return database_url


def run_migrations_offline() -> None:
    """Generate migration SQL without connecting."""

    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={
            "paramstyle": "named",
        },
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(
    connection: Connection,
) -> None:
    """Run migrations with one synchronous connection facade."""

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create a temporary async engine for migrations."""

    connectable = create_async_engine(
        get_database_url(),
        poolclass=pool.NullPool,
    )

    try:
        async with connectable.connect() as connection:
            await connection.run_sync(
                do_run_migrations,
            )
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations against the configured database."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
