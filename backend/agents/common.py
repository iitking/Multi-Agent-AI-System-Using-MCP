"""Helpers shared by all agents."""
from __future__ import annotations

from typing import Any

from backend.graph.state import WorkflowState
from backend.mcp_client import ToolContext
from backend.services.audit import now_iso


def make_result(
    agent: str,
    status: str = "ok",
    findings: list[Any] | None = None,
    evidence: list[Any] | None = None,
    errors: list[str] | None = None,
    next_action: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Structured agent output: status, findings, evidence, errors, next_action (+ agent-specific fields)."""
    return {
        "agent": agent,
        "status": status,  # ok | degraded | error
        "findings": findings or [],
        "evidence": evidence or [],
        "errors": errors or [],
        "next_action": next_action,
        **extra,
    }


def event(agent: str, message: str, status: str = "ok") -> dict[str, Any]:
    return {"ts": now_iso(), "agent": agent, "status": status, "message": message}


def tool_context(state: WorkflowState, agent: str) -> ToolContext:
    return ToolContext(run_id=state["run_id"], user=state.get("user", "system"), agent=agent)
