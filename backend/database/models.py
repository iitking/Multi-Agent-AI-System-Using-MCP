"""Application tables: runs and the audit log (separate from the analytics data)."""
from __future__ import annotations

from sqlalchemy import Column, Integer, MetaData, String, Table, Text

from backend.database.db import get_app_engine

app_metadata = MetaData()

runs = Table(
    "runs",
    app_metadata,
    Column("id", String(64), primary_key=True),
    Column("user", String(64), nullable=False),
    Column("request", Text, nullable=False),
    Column("status", String(32), nullable=False, index=True),
    Column("created_at", String(32), nullable=False),
    Column("updated_at", String(32), nullable=False),
    Column("plan", Text),
    Column("result", Text),
    Column("report_markdown", Text),
    Column("report_path", String(255)),
    Column("external_action", Text),
    Column("metrics", Text),
    Column("events", Text),
    Column("error", Text),
)

audit_log = Table(
    "audit_log",
    app_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ts", String(32), nullable=False, index=True),
    Column("run_id", String(64), index=True),
    Column("actor", String(64), nullable=False),
    Column("agent", String(64)),
    Column("action", String(64), nullable=False),
    Column("tool", String(128)),
    Column("status", String(32), nullable=False),
    Column("detail", Text),
    Column("duration_ms", Integer),
)


def init_app_db() -> None:
    app_metadata.create_all(get_app_engine())
