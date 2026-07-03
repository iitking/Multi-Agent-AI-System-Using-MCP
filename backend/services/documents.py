"""Report assembly and storage. Used by the Document MCP server."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend.config import get_settings

RUN_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
MAX_REPORT_BYTES = 500_000


def _clean(value: Any, limit: int = 5000) -> str:
    return str(value).replace("\r", "").strip()[:limit]


def _cell(value: Any) -> str:
    return _clean(value, 300).replace("|", "\\|").replace("\n", " ")


def build_markdown(title: str, sections: list[dict[str, Any]], metadata: dict[str, Any] | None = None) -> str:
    if not isinstance(sections, list) or len(sections) > 30:
        raise ValueError("sections must be a list with at most 30 entries.")
    lines = [f"# {_clean(title, 200)}", ""]
    if metadata:
        lines += ["> " + " · ".join(f"{_clean(k, 40)}: {_clean(v, 120)}" for k, v in metadata.items()), ""]
    for section in sections:
        lines += [f"## {_clean(section.get('heading', 'Section'), 200)}", ""]
        if section.get("body"):
            lines += [_clean(section["body"]), ""]
        bullets = section.get("bullets") or []
        if bullets:
            lines += [f"- {_clean(b, 1200)}" for b in bullets] + [""]
        table = section.get("table")
        if table and table.get("columns"):
            columns = [_cell(c) for c in table["columns"]]
            lines += ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
            for row in table.get("rows", []):
                lines.append("| " + " | ".join(_cell(c) for c in row) + " |")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def save_markdown(run_id: str, markdown: str) -> dict[str, Any]:
    if not RUN_ID_RE.match(run_id or ""):
        raise ValueError("Invalid run_id.")
    data = markdown.encode("utf-8")
    if len(data) > MAX_REPORT_BYTES:
        raise ValueError("Report is too large.")
    reports_dir = get_settings().reports_dir
    reports_dir.mkdir(parents=True, exist_ok=True)
    target = (reports_dir / f"{run_id}.md").resolve()
    if reports_dir.resolve() not in target.parents:
        raise ValueError("Invalid report path.")
    Path(target).write_bytes(data)
    return {"path": f"reports/{target.name}", "bytes": len(data)}
