"""Data Analyst agent: queries approved data through the Data MCP server (read-only tools only)."""
from __future__ import annotations

import asyncio
from typing import Any

from backend.agents.common import event, make_result, tool_context
from backend.graph.state import WorkflowState
from backend.mcp_client import ToolCallError, call_tool
from backend.security.permissions import PermissionDenied

MIN_DROP_PCT = -5.0  # a month-over-month decline smaller than this is not treated as a "drop"


def detect_drop_window(months: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Find the largest month-over-month decline and the window over which revenue stayed below baseline.

    Baseline = up to 3 months before the decline. The comparison window starts at the decline and
    continues while revenue remains below the baseline average.
    """
    if len(months) < 4:
        return None
    revenues = [m["revenue"] for m in months]
    worst_index, worst_pct = None, 0.0
    for i in range(1, len(revenues)):
        pct = (revenues[i] - revenues[i - 1]) / revenues[i - 1] * 100 if revenues[i - 1] else 0.0
        if pct < worst_pct:
            worst_index, worst_pct = i, pct
    if worst_index is None or worst_pct > MIN_DROP_PCT:
        return None
    baseline = months[max(0, worst_index - 3) : worst_index]
    if not baseline:
        return None
    baseline_avg = sum(m["revenue"] for m in baseline) / len(baseline)
    end_index = worst_index
    while end_index + 1 < len(revenues) and revenues[end_index + 1] < baseline_avg:
        end_index += 1
    return {
        "baseline_start": baseline[0]["month"],
        "baseline_end": baseline[-1]["month"],
        "comparison_start": months[worst_index]["month"],
        "comparison_end": months[end_index]["month"],
        "largest_mom_decline_pct": round(worst_pct, 2),
    }


async def run(state: WorkflowState) -> dict[str, Any]:
    plan = state.get("plan", {})
    intents = plan.get("intents", [])
    ctx = tool_context(state, "data_analyst")
    evidence: list[dict[str, Any]] = []

    time_period = plan.get("time_period")
    period_args: dict[str, Any] = {}
    if time_period:
        if time_period.get("start_month"):
            period_args["start_month"] = time_period["start_month"]
        if time_period.get("end_month"):
            period_args["end_month"] = time_period["end_month"]

    try:
        unrecognized_concept = plan.get("unrecognized_concept")
        if unrecognized_concept:
            full_summary = await call_tool(ctx, "data", "get_sales_summary", {})
            evidence.append({"tool": "data.get_sales_summary", "args": {}})
            full_months = full_summary.get("months", [])
            avail_start = full_months[0]["month"] if full_months else "2025-01"
            avail_end = full_months[-1]["month"] if full_months else "2025-12"
            data: dict[str, Any] = {
                "unrecognized_concept": unrecognized_concept,
                "concept_found_in_data": False,
                "available_start": avail_start,
                "available_end": avail_end,
                "available_revenue": full_summary.get("total_revenue", 0.0),
                "available_units": full_summary.get("total_units", 0),
                "kpis": None,
                "monthly": [],
                "drop_window": None,
                "comparisons": {},
                "top_products": None,
            }
            msg = f"Queried sales database: no transactions or catalog entries found for '{unrecognized_concept}'."
            findings = [{"id": "D1", "statement": msg}]
            result = make_result("data_analyst", findings=findings, evidence=evidence, next_action="insight", data=data)
            return {
                "data_result": result,
                "tool_calls": ctx.calls,
                "events": [event("data_analyst", msg)],
            }

        # Check summary for requested period (or all data if none specified)
        summary = await call_tool(ctx, "data", "get_sales_summary", period_args)
        evidence.append({"tool": "data.get_sales_summary", "args": period_args})

        # If user explicitly asked for a period (e.g. 2020) and no transactions exist:
        if period_args and summary.get("month_count", 0) == 0:
            full_summary = await call_tool(ctx, "data", "get_sales_summary", {})
            evidence.append({"tool": "data.get_sales_summary", "args": {}})
            full_months = full_summary.get("months", [])
            avail_start = full_months[0]["month"] if full_months else "N/A"
            avail_end = full_months[-1]["month"] if full_months else "N/A"
            p_label = time_period.get("label", time_period.get("year", "the requested period"))
            data: dict[str, Any] = {
                "no_data_for_period": True,
                "requested_period": time_period,
                "available_start": avail_start,
                "available_end": avail_end,
                "available_revenue": full_summary.get("total_revenue", 0.0),
                "available_units": full_summary.get("total_units", 0),
                "kpis": None,
                "monthly": [],
                "drop_window": None,
                "comparisons": {},
                "top_products": None,
            }
            msg = f"No sales data found for {p_label}. Available records cover {avail_start} to {avail_end}."
            findings = [{"id": "D1", "statement": msg}]
            result = make_result("data_analyst", findings=findings, evidence=evidence, next_action="insight", data=data)
            return {
                "data_result": result,
                "tool_calls": ctx.calls,
                "events": [event("data_analyst", msg)],
            }

        kpis = await call_tool(ctx, "data", "calculate_kpis", period_args)
        evidence.append({"tool": "data.calculate_kpis", "args": period_args})
        months = summary["months"]
        data = {"monthly": months, "kpis": kpis, "drop_window": None, "comparisons": {},
                "top_products": None, "top_products_window": None}
        findings = [{"id": "D1", "statement": f"Loaded {len(months)} months of sales data."}]

        window = detect_drop_window(months) if "revenue_drop" in intents else None
        data["drop_window"] = window

        jobs: dict[str, Any] = {
            "by_region": call_tool(ctx, "data", "revenue_by_dimension", {"dimension": "region", **period_args}),
            "by_category": call_tool(ctx, "data", "revenue_by_dimension", {"dimension": "category", **period_args}),
            "top_products": call_tool(ctx, "data", "top_products", {"limit": 5, **period_args}),
        }
        evidence.append({"tool": "data.revenue_by_dimension", "args": {"dimension": "region", **period_args}})
        evidence.append({"tool": "data.revenue_by_dimension", "args": {"dimension": "category", **period_args}})
        evidence.append({"tool": "data.top_products", "args": {"limit": 5, **period_args}})

        if window:
            for dimension in plan.get("dimensions", []):
                args = {"dimension": dimension, "baseline_start": window["baseline_start"],
                        "baseline_end": window["baseline_end"], "comparison_start": window["comparison_start"],
                        "comparison_end": window["comparison_end"]}
                jobs[f"cmp:{dimension}"] = call_tool(ctx, "data", "period_comparison", args)
                evidence.append({"tool": "data.period_comparison", "args": args})
            window_args = {"limit": 5, "start_month": window["comparison_start"], "end_month": window["comparison_end"]}
            jobs["top_products_window"] = call_tool(ctx, "data", "top_products", window_args)
            evidence.append({"tool": "data.top_products", "args": window_args})
            findings.append({"id": "D2", "statement": (
                f"Largest month-over-month decline: {window['largest_mom_decline_pct']}% "
                f"starting {window['comparison_start']}.")})

        results = dict(zip(jobs, await asyncio.gather(*jobs.values())))
        for key, value in results.items():
            if key.startswith("cmp:"):
                data["comparisons"][key.split(":", 1)[1]] = value
            else:
                data[key] = value

        result = make_result("data_analyst", findings=findings, evidence=evidence, next_action="insight", data=data)
        return {
            "data_result": result,
            "tool_calls": ctx.calls,
            "events": [event("data_analyst", f"Ran {len(ctx.calls)} MCP tool calls"
                             + (f"; drop window {window['comparison_start']}..{window['comparison_end']}" if window else ""))],
        }
    except (ToolCallError, PermissionDenied, KeyError) as exc:
        message = f"Data analysis failed: {type(exc).__name__}: {exc}"[:300]
        return {
            "data_result": make_result("data_analyst", status="error", errors=[message], evidence=evidence,
                                       next_action="abort"),
            "tool_calls": ctx.calls,
            "errors": [message],
            "events": [event("data_analyst", message, "error")],
        }
