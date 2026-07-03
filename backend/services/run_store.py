"""Persistence for workflow runs."""
from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import insert, select, update

from backend.database.db import get_app_engine
from backend.database.models import runs
from backend.services.audit import now_iso

JSON_FIELDS = {"plan", "result", "external_action", "metrics", "events"}


def _decode(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for field in JSON_FIELDS:
        if out.get(field):
            out[field] = json.loads(out[field])
    return out


def new_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:12]}"


def create_run(user: str, request: str) -> str:
    run_id = new_run_id()
    now = now_iso()
    with get_app_engine().begin() as conn:
        conn.execute(
            insert(runs).values(
                id=run_id, user=user, request=request, status="queued", created_at=now, updated_at=now
            )
        )
    return run_id


def update_run(run_id: str, **fields: Any) -> None:
    values = {k: (json.dumps(v, default=str) if k in JSON_FIELDS and v is not None else v) for k, v in fields.items()}
    values["updated_at"] = now_iso()
    with get_app_engine().begin() as conn:
        conn.execute(update(runs).where(runs.c.id == run_id).values(**values))


def get_run(run_id: str) -> dict[str, Any] | None:
    with get_app_engine().connect() as conn:
        row = conn.execute(select(runs).where(runs.c.id == run_id)).first()
    return _decode(dict(row._mapping)) if row else None


def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    query = select(runs).order_by(runs.c.created_at.desc()).limit(max(1, min(limit, 200)))
    with get_app_engine().connect() as conn:
        return [_decode(dict(r._mapping)) for r in conn.execute(query)]
