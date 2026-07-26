from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


def create_database_engine(
    database_url: str | None = None,
    *,
    echo: bool | None = None,
) -> AsyncEngine:
    """Create a non-connected asynchronous PostgreSQL engine."""

    selected_url = (
        database_url if database_url is not None else settings.database_url.get_secret_value()
    ).strip()

    if not selected_url:
        raise ValueError("Database URL must not be empty.")

    try:
        parsed_url = make_url(selected_url)
    except ArgumentError as error:
        raise ValueError("Invalid database URL.") from error

    if parsed_url.drivername != "postgresql+asyncpg":
        raise ValueError("Database URL must use the postgresql+asyncpg driver.")

    selected_echo = echo if echo is not None else settings.database_echo

    return create_async_engine(
        selected_url,
        echo=selected_echo,
        pool_pre_ping=True,
    )


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Create sessions bound to one asynchronous engine."""

    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autoflush=False,
        expire_on_commit=False,
    )
