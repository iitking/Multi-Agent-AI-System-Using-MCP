"""MCP client used by the agents.

Every call: (1) checks the per-agent tool allowlist, (2) launches the MCP server over stdio,
(3) enforces a timeout, (4) records an audit entry and a metrics record.

One short-lived server process per call keeps the code simple and avoids cross-task async
context problems. For higher throughput, keep long-lived sessions per server (see README).
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from backend.config import ROOT, get_settings
from backend.security.permissions import PermissionDenied, assert_tool_allowed
from backend.services import audit

try:  # LangSmith spans for tool calls when tracing is enabled
    from langsmith import traceable
except ImportError:  # pragma: no cover
    def traceable(*_args, **_kwargs):  # type: ignore[no-redef]
        return lambda fn: fn

SERVER_MODULES = {
    "data": "backend.mcp_servers.data_server",
    "research": "backend.mcp_servers.research_server",
    "document": "backend.mcp_servers.document_server",
}

_CHILD_ENV_KEYS = (
    "PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL",
    "VIRTUAL_ENV", "DATA_DIR", "DOCS_DIR", "REPORTS_DIR",
    "ANALYTICS_DATABASE_URL", "ANALYTICS_READONLY_DATABASE_URL",
)


class ToolCallError(Exception):
    """A tool call failed (server error, validation error or timeout)."""


@dataclass
class ToolContext:
    run_id: str
    user: str
    agent: str
    calls: list[dict[str, Any]] = field(default_factory=list)


def _server_params(module: str) -> StdioServerParameters:
    env = {k: os.environ[k] for k in _CHILD_ENV_KEYS if k in os.environ}
    env["PYTHONPATH"] = str(ROOT)
    env["PYTHONUNBUFFERED"] = "1"
    return StdioServerParameters(command=sys.executable, args=["-m", module], env=env, cwd=str(ROOT))


def _parse_result(result: Any) -> dict[str, Any]:
    texts = [c.text for c in result.content if getattr(c, "type", "") == "text"]
    if result.isError:
        raise ToolCallError((" ".join(texts) or "tool returned an error")[:500])
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict) and structured:
        return structured["result"] if set(structured) == {"result"} and isinstance(structured["result"], dict) else structured
    if not texts:
        raise ToolCallError("tool returned no content")
    try:
        parsed = json.loads(texts[0])
    except json.JSONDecodeError as exc:
        raise ToolCallError("tool returned non-JSON output") from exc
    return parsed if isinstance(parsed, dict) else {"result": parsed}


@traceable(name="mcp_tool_call", run_type="tool")
async def call_tool(
    ctx: ToolContext, server: str, tool: str, arguments: dict[str, Any] | None = None
) -> dict[str, Any]:
    started = time.perf_counter()
    record: dict[str, Any] = {
        "agent": ctx.agent, "server": server, "tool": tool, "ok": False, "duration_ms": 0, "error": None,
    }
    try:
        assert_tool_allowed(ctx.agent, server, tool)
        module = SERVER_MODULES.get(server)
        if module is None:
            raise ToolCallError(f"unknown MCP server '{server}'")
        timeout = get_settings().mcp_tool_timeout
        with anyio.fail_after(timeout):
            async with stdio_client(_server_params(module)) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool, arguments or {})
        payload = _parse_result(result)
        record["ok"] = True
        return payload
    except PermissionDenied as exc:
        record["error"] = f"permission_denied: {exc}"
        raise
    except TimeoutError:
        record["error"] = "timeout"
        raise ToolCallError(f"{server}.{tool} timed out after {get_settings().mcp_tool_timeout}s") from None
    except ToolCallError as exc:
        record["error"] = str(exc)[:300]
        raise
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"[:300]
        raise ToolCallError(f"{server}.{tool} failed: {type(exc).__name__}") from exc
    finally:
        record["duration_ms"] = int((time.perf_counter() - started) * 1000)
        ctx.calls.append(record)
        audit.record(
            ctx.run_id,
            ctx.user,
            "tool_call",
            agent=ctx.agent,
            tool=f"{server}.{tool}",
            status="ok" if record["ok"] else "error",
            detail=json.dumps({"args": arguments or {}, "error": record["error"]}, default=str),
            duration_ms=record["duration_ms"],
        )


async def discover_tools() -> dict[str, list[dict[str, Any]]]:
    """MCP tool discovery across all servers (used by GET /api/tools)."""
    catalog: dict[str, list[dict[str, Any]]] = {}
    for server, module in SERVER_MODULES.items():
        with anyio.fail_after(get_settings().mcp_tool_timeout):
            async with stdio_client(_server_params(module)) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listed = await session.list_tools()
        catalog[server] = [{"name": t.name, "description": (t.description or "").strip()} for t in listed.tools]
    return catalog
