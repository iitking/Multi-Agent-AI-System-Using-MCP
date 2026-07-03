"""Audit trail: who/which agent did what, when, with what outcome."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import insert, select

from backend.database.db import get_app_engine
from backend.database.models import audit_log
from backend.security.guard import redact


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def record(
    run_id: str | None,
    actor: str,
    action: str,
    *,
    agent: str | None = None,
    tool: str | None = None,
    status: str = "ok",
    detail: Any = None,
    duration_ms: int | None = None,
) -> None:
    """Best-effort write. Secrets are redacted; auditing must never break a run."""
    if detail is not None and not isinstance(detail, str):
        detail = json.dumps(detail, default=str)
    try:
        with get_app_engine().begin() as conn:
            conn.execute(
                insert(audit_log).values(
                    ts=now_iso(),
                    run_id=run_id,
                    actor=actor,
                    agent=agent,
                    action=action,
                    tool=tool,
                    status=status,
                    detail=redact(detail) if detail else None,
                    duration_ms=duration_ms,
                )
            )
    except Exception:  # pragma: no cover - audit failures are logged, not raised
        import logging

        logging.getLogger("audit").exception("failed to write audit entry")


def list_entries(run_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    query = select(audit_log).order_by(audit_log.c.id.desc()).limit(max(1, min(limit, 1000)))
    if run_id:
        query = query.where(audit_log.c.run_id == run_id)
    with get_app_engine().connect() as conn:
        return [dict(row._mapping) for row in conn.execute(query)]
