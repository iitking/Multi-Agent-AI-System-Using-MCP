"""Research agent: retrieves approved company context through the Research MCP server."""
from __future__ import annotations

import asyncio
from typing import Any

from backend.agents.common import event, make_result, tool_context
from backend.graph.state import WorkflowState
from backend.mcp_client import ToolCallError, call_tool


async def run(state: WorkflowState) -> dict[str, Any]:
    queries = (state.get("plan") or {}).get("research_queries", [])[:4]
    ctx = tool_context(state, "researcher")
    outcomes = await asyncio.gather(
        *(call_tool(ctx, "research", "search_company_docs", {"query": q, "limit": 3}) for q in queries),
        return_exceptions=True,
    )

    best: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for query, outcome in zip(queries, outcomes):
        if isinstance(outcome, ToolCallError):
            errors.append(f"search '{query}' failed: {outcome}"[:300])
            continue
        if isinstance(outcome, BaseException):
            raise outcome
        for hit in outcome.get("results", []):
            if hit["source"] not in best or hit["score"] > best[hit["source"]]["score"]:
                best[hit["source"]] = hit

    documents = sorted(best.values(), key=lambda d: (-d["score"], d["source"]))
    flagged = [d["source"] for d in documents if d.get("flagged")]
    status = "ok" if not errors else ("degraded" if documents else "error")
    result = make_result(
        "researcher",
        status=status,
        findings=[f"Retrieved {len(documents)} documents ({len(flagged)} flagged as untrusted)."],
        evidence=[{"tool": "research.search_company_docs", "args": {"query": q}} for q in queries],
        errors=errors,
        next_action="insight",
        documents=documents,
        flagged_sources=flagged,
    )
    message = f"Retrieved {len(documents)} documents"
    if flagged:
        message += f"; withheld {len(flagged)} flagged as possible prompt injection: {', '.join(flagged)}"
    return {
        "research_result": result,
        "tool_calls": ctx.calls,
        "errors": errors,
        "events": [event("researcher", message, "ok" if status == "ok" else "degraded")],
    }
