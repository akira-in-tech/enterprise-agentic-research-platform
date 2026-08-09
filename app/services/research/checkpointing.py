from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from pydantic import SecretStr
from sqlalchemy.engine import make_url


def create_langgraph_postgres_url(database_url: SecretStr) -> str:
    """Convert the SQLAlchemy asyncpg URL into a psycopg connection URL."""

    url = make_url(database_url.get_secret_value())
    if url.get_backend_name() != "postgresql":
        raise ValueError("LangGraph checkpoints require a PostgreSQL database URL.")

    # asyncpg's connect() takes an `ssl` query parameter; raw psycopg/libpq
    # rejects it outright and expects `sslmode` instead. Their value sets
    # overlap ("require", "disable", "verify-full", ...), so a key rename
    # is sufficient here -- this is the one query parameter this project's
    # asyncpg URLs ever set (see entrypoint.build_managed_database_url).
    query = dict(url.query)
    if "ssl" in query:
        query["sslmode"] = query.pop("ssl")

    return url.set(drivername="postgresql", query=query).render_as_string(hide_password=False)


@asynccontextmanager
async def open_langgraph_checkpointer(
    database_url: SecretStr,
) -> AsyncIterator[AsyncPostgresSaver]:
    """Open and migrate the official asynchronous PostgreSQL checkpointer."""

    connection_url = create_langgraph_postgres_url(database_url)
    async with AsyncPostgresSaver.from_conn_string(connection_url) as checkpointer:
        await checkpointer.setup()
        yield checkpointer
