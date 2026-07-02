"""Database engines.

Two logically separate databases are used:

* the **analytics** database (business data) - agents only ever reach it through a
  *read-only* engine, and only via MCP tools;
* the **app** database (runs, audit log) - written by the API only.

Both default to SQLite files so the project runs with zero setup. Point the URLs at
PostgreSQL (``postgresql+psycopg://...``) for real deployments.
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url

from backend.config import get_settings

_ENGINES: dict[str, Engine] = {}


def _build(key: str, url: str, **kwargs) -> Engine:
    if key not in _ENGINES:
        if make_url(url).get_backend_name() == "sqlite":
            kwargs.setdefault("connect_args", {"check_same_thread": False})
        _ENGINES[key] = create_engine(url, pool_pre_ping=True, **kwargs)
    return _ENGINES[key]


def reset_engines() -> None:
    """Dispose cached engines (used by tests)."""
    for engine in _ENGINES.values():
        engine.dispose()
    _ENGINES.clear()


def get_app_engine() -> Engine:
    return _build("app", get_settings().app_db_url)


def get_analytics_write_engine() -> Engine:
    """Writable engine. Only the seeding script should use this."""
    return _build("analytics_write", get_settings().analytics_db_url)


def get_analytics_readonly_engine() -> Engine:
    """Read-only engine used by the Data MCP server."""
    settings = get_settings()
    url = settings.analytics_readonly_db_url or settings.analytics_db_url
    parsed = make_url(url)

    if parsed.get_backend_name() == "sqlite":
        path = parsed.database
        if not path or not Path(path).exists():
            raise RuntimeError(
                "Analytics database not found. Run `python -m backend.database.seed` first."
            )
        return _build("analytics_ro", f"sqlite:///file:{path}?mode=ro&uri=true")

    # PostgreSQL: force read-only transactions even if the role has write privileges.
    return _build(
        "analytics_ro",
        url,
        connect_args={"options": "-c default_transaction_read_only=on"},
    )


def database_file_exists(url: str) -> bool:
    parsed = make_url(url)
    return parsed.get_backend_name() != "sqlite" or bool(parsed.database and os.path.exists(parsed.database))
