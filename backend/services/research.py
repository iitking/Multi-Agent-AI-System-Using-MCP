"""Search over approved company documents (markdown files). Used by the Research MCP server.

Retrieved text is *untrusted*: every snippet is screened for prompt-injection patterns and
withheld if flagged.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend.config import get_settings
from backend.security.guard import sanitize_untrusted, scan_untrusted

_STOP = {"the", "and", "for", "with", "that", "this", "from", "are", "was", "were", "our", "why", "what", "how", "have", "has"}


def _doc_paths() -> list[Path]:
    docs_dir = get_settings().docs_dir
    return sorted(docs_dir.glob("*.md")) if docs_dir.exists() else []


def _title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("#"):
            return line.lstrip("# ").strip()[:120]
    return fallback


def list_documents() -> dict[str, Any]:
    docs = []
    for path in _doc_paths():
        content = path.read_text(encoding="utf-8", errors="replace")
        docs.append({"name": path.name, "title": _title(content, path.stem), "bytes": len(content.encode("utf-8"))})
    return {"documents": docs}


def search_documents(query: str, limit: int = 3) -> dict[str, Any]:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string.")
    limit = max(1, min(int(limit), 5))
    terms = {t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 2 and t not in _STOP}
    if not terms:
        raise ValueError("query contains no searchable terms.")

    results: list[dict[str, Any]] = []
    for path in _doc_paths():
        content = path.read_text(encoding="utf-8", errors="replace")
        best_score, best_paragraph = 0, ""
        for paragraph in re.split(r"\n\s*\n", content):
            words = set(re.findall(r"[a-z0-9]+", paragraph.lower()))
            score = len(terms & words)
            if score > best_score:
                best_score, best_paragraph = score, paragraph.strip()
        if best_score == 0:
            continue
        # Score the *original* paragraph, but never return flagged text.
        cleaned = sanitize_untrusted(best_paragraph, max_len=500)
        results.append(
            {
                "source": path.name,
                "title": _title(content, path.stem),
                "score": best_score,
                "snippet": cleaned.text,
                "flagged": cleaned.flagged,
                "flag_reasons": cleaned.reasons or scan_untrusted(best_paragraph),
            }
        )
    results.sort(key=lambda r: (-r["score"], r["source"]))
    return {"query": query, "results": results[:limit]}
