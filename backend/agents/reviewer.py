"""Reviewer agent: independently re-verifies figures, evidence and completeness.

It re-runs the ``verify`` spec attached to each finding through MCP (with its own, narrower tool
allowlist) and compares the live results with what the Insight agent claimed.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from backend.agents.common import event, make_result, tool_context
from backend.graph.state import WorkflowState
from backend.mcp_client import ToolCallError, call_tool
from backend.security.permissions import PermissionDenied

_SELECTOR = re.compile(r"^(\w+)\[(?:(\w+)=([^\]]+)|(\d+))\]$")
TOLERANCE = 0.011  # money is rounded to cents


def get_path(obj: Any, path: str) -> Any:
    """Tiny path language: ``a.b``, ``rows[name=West].change``, ``items[0].name``."""
    current = obj
    for token in path.split("."):
        match = _SELECTOR.match(token)
        if not match:
            current = current[token]
            continue
        key, sel_key, sel_value, index = match.groups()
        current = current[key]
        if index is not None:
            current = current[int(index)]
        else:
            current = next(item for item in current if str(item.get(sel_key)) == sel_value)
    return current


def values_match(actual: Any, expected: Any) -> bool:
    numeric = (int, float)
    if isinstance(actual, numeric) and isinstance(expected, numeric) and not isinstance(actual, bool):
        return abs(actual - expected) <= TOLERANCE
    return actual == expected


async def run(state: WorkflowState) -> dict[str, Any]:
    plan = state.get("plan") or {}
    data_result = state.get("data_result") or {}
    insight = state.get("insight_result") or {}
    research = state.get("research_result") or {}
    ctx = tool_context(state, "reviewer")
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "passed": bool(ok), "detail": detail})

    # Fatal: nothing to verify.
    if data_result.get("status") != "ok" or insight.get("status") == "error":
        add("data_available", False, "; ".join(data_result.get("errors", [])) or "analysis did not complete")
        review = {"passed": False, "fatal": True, "checks": checks, "issues": [c["detail"] for c in checks]}
        return {"review_result": review, "status": "review_failed",
                "events": [event("reviewer", "Aborting: no verifiable analysis", "error")]}

    findings = insight.get("findings", [])
    add("findings_present", len(findings) > 0, "no findings produced" if not findings else f"{len(findings)} findings")

    no_data = bool(data_result.get("data", {}).get("no_data_for_period"))
    if "revenue_drop" in plan.get("intents", []) and not no_data:
        types = {f["type"] for f in findings}
        add("drop_analysis_present", bool({"drop_summary", "no_drop"} & types), "revenue-drop question needs a drop summary")
        if "drop_summary" in types:
            add("drivers_identified", "driver" in types, "no decliner was identified")

    # Independent numeric verification: unique tool calls, run in parallel.
    specs = {f["id"]: f["verify"] for f in findings if f.get("verify")}
    unique: dict[str, dict[str, Any]] = {}
    for spec in specs.values():
        unique[json.dumps([spec["server"], spec["tool"], spec["args"]], sort_keys=True)] = spec
    keys = list(unique)
    outcomes = await asyncio.gather(
        *(call_tool(ctx, unique[k]["server"], unique[k]["tool"], unique[k]["args"]) for k in keys),
        return_exceptions=True,
    )
    live = dict(zip(keys, outcomes))
    for fid, spec in specs.items():
        outcome = live[json.dumps([spec["server"], spec["tool"], spec["args"]], sort_keys=True)]
        if isinstance(outcome, (ToolCallError, PermissionDenied)):
            add(f"verify_{fid}", False, f"verification call failed: {outcome}"[:200])
            continue
        if isinstance(outcome, BaseException):
            raise outcome
        mismatches = []
        for path, expected in spec["expect"].items():
            try:
                actual = get_path(outcome, path)
            except (KeyError, IndexError, StopIteration, TypeError):
                mismatches.append(f"{path}: not found")
                continue
            if not values_match(actual, expected):
                mismatches.append(f"{path}: claimed {expected!r}, data says {actual!r}")
        add(f"verify_{fid}", not mismatches, "; ".join(mismatches) if mismatches else "matches live data")

    # Hypotheses must cite an approved, unflagged document that was actually retrieved.
    approved = {d["source"] for d in research.get("documents", []) if not d.get("flagged")}
    bad = [h["source"] for h in insight.get("hypotheses", []) if h["source"] not in approved]
    add("hypothesis_sources", not bad, f"uncited or untrusted sources: {bad}" if bad else "all sources approved")

    # Recommendations must be tied to findings.
    ids = {f["id"] for f in findings}
    orphan = [r["text"][:60] for r in insight.get("recommendations", []) if not set(r["based_on"]) <= ids]
    add("recommendations_grounded", not orphan, f"not tied to findings: {orphan}" if orphan else "all grounded")

    issues = [f"{c['name']}: {c['detail']}" for c in checks if not c["passed"]]
    passed = not issues
    review = {"passed": passed, "fatal": False, "checks": checks, "issues": issues}
    update: dict[str, Any] = {
        "review_result": review,
        "tool_calls": ctx.calls,
        "events": [event("reviewer", f"{sum(c['passed'] for c in checks)}/{len(checks)} checks passed",
                         "ok" if passed else "failed")],
    }
    if not passed:
        update["retry_count"] = state.get("retry_count", 0) + 1
        update["review_feedback"] = issues
    return update
