import os
import subprocess
import sys
from collections.abc import Mapping, MutableMapping
from typing import NoReturn
from urllib.parse import quote

from sqlalchemy import URL


def _require_complete_group(
    values: Mapping[str, str],
    names: tuple[str, ...],
    *,
    group_name: str,
) -> dict[str, str] | None:
    selected = {name: values.get(name, "").strip() for name in names}
    configured = [name for name, value in selected.items() if value]

    if not configured:
        return None

    missing = [name for name, value in selected.items() if not value]
    if missing:
        missing_names = ", ".join(missing)
        raise RuntimeError(f"Incomplete {group_name} configuration; missing: {missing_names}.")

    return selected


def build_managed_database_url(values: Mapping[str, str]) -> str | None:
    """Build an encoded async PostgreSQL URL from injected container secrets."""

    selected = _require_complete_group(
        values,
        (
            "POSTGRES_HOST",
            "POSTGRES_DB",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
        ),
        group_name="PostgreSQL",
    )
    if selected is None:
        return None

    url = URL.create(
        drivername="postgresql+asyncpg",
        username=selected["POSTGRES_USER"],
        password=selected["POSTGRES_PASSWORD"],
        host=selected["POSTGRES_HOST"],
        port=5432,
        database=selected["POSTGRES_DB"],
        query={"ssl": "require"},
    )
    return url.render_as_string(hide_password=False)


def build_managed_redis_url(values: Mapping[str, str]) -> str | None:
    """Build a TLS Redis URL from an injected cache token."""

    selected = _require_complete_group(
        values,
        (
            "REDIS_HOST",
            "REDIS_AUTH_TOKEN",
        ),
        group_name="Redis",
    )
    if selected is None:
        return None

    encoded_token = quote(selected["REDIS_AUTH_TOKEN"], safe="")
    return f"rediss://:{encoded_token}@{selected['REDIS_HOST']}:6379/0"


def configure_runtime_environment(
    environ: MutableMapping[str, str] | None = None,
) -> None:
    """Populate service URLs without overriding explicit local configuration."""

    selected_environ = os.environ if environ is None else environ

    if not selected_environ.get("DATABASE_URL", "").strip():
        database_url = build_managed_database_url(selected_environ)
        if database_url is not None:
            selected_environ["DATABASE_URL"] = database_url

    if not selected_environ.get("REDIS_URL", "").strip():
        redis_url = build_managed_redis_url(selected_environ)
        if redis_url is not None:
            selected_environ["REDIS_URL"] = redis_url


def main() -> NoReturn:
    """Run migrations, then replace this process with the API server."""

    configure_runtime_environment()
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
    )
    os.execv(
        sys.executable,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
        ],
    )


if __name__ == "__main__":
    main()
