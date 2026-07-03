"""Business analytics over the sales table. Pure functions, read-only, used by the Data MCP server."""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from backend.database.db import get_analytics_readonly_engine
from backend.security.sql_guard import validate_readonly_sql

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
DIMENSIONS = {"region", "product", "category"}
ALLOWED_TABLES = {"sales"}
MAX_ROWS = 200


class AnalyticsError(ValueError):
    """Invalid arguments or no data. Safe to show to the caller."""


# --------------------------------------------------------------------------- helpers
def _month(value: str | None, default: str | None = None) -> str:
    if value is None:
        if default is None:
            raise AnalyticsError("A month in YYYY-MM format is required.")
        return default
    if not isinstance(value, str) or not MONTH_RE.match(value):
        raise AnalyticsError(f"Invalid month '{value}'. Use YYYY-MM (e.g. 2025-09).")
    return value


def _dimension(value: str) -> str:
    if value not in DIMENSIONS:
        raise AnalyticsError(f"Unknown dimension '{value}'. Allowed: {sorted(DIMENSIONS)}.")
    return value


def _json(value: Any) -> Any:
    return float(value) if isinstance(value, Decimal) else value


def _query(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    with get_analytics_readonly_engine().connect() as conn:
        result = conn.execute(text(sql), params or {})
        return [{k: _json(v) for k, v in row._mapping.items()} for row in result]


def _range(start_month: str | None, end_month: str | None) -> tuple[str, str]:
    start, end = _month(start_month, "0000-00"), _month(end_month, "9999-99")
    if start > end:
        raise AnalyticsError("start_month must not be after end_month.")
    return start, end


# --------------------------------------------------------------------------- tools
def sales_summary(start_month: str | None = None, end_month: str | None = None) -> dict[str, Any]:
    s, e = _range(start_month, end_month)
    params = {"s": s, "e": e}
    totals = _query(
        "SELECT COALESCE(SUM(revenue), 0) AS revenue, COALESCE(SUM(units), 0) AS units "
        "FROM sales WHERE month >= :s AND month <= :e",
        params,
    )[0]
    rows = _query(
        "SELECT month, SUM(revenue) AS revenue, SUM(units) AS units FROM sales "
        "WHERE month >= :s AND month <= :e GROUP BY month ORDER BY month",
        params,
    )
    months = [
        {"month": r["month"], "revenue": round(float(r["revenue"]), 2), "units": int(r["units"])} for r in rows
    ]
    return {
        "total_revenue": round(float(totals["revenue"]), 2),
        "total_units": int(totals["units"]),
        "month_count": len(months),
        "months": months,
    }


def revenue_by_dimension(
    dimension: str, start_month: str | None = None, end_month: str | None = None
) -> dict[str, Any]:
    col = _dimension(dimension)  # allowlisted, so safe to interpolate
    s, e = _range(start_month, end_month)
    rows = _query(
        f"SELECT {col} AS name, SUM(revenue) AS revenue, SUM(units) AS units FROM sales "
        f"WHERE month >= :s AND month <= :e GROUP BY {col} ORDER BY revenue DESC, name ASC",
        {"s": s, "e": e},
    )
    total = sum(float(r["revenue"]) for r in rows)
    items = [
        {
            "name": r["name"],
            "revenue": round(float(r["revenue"]), 2),
            "units": int(r["units"]),
            "share_pct": round(float(r["revenue"]) / total * 100, 2) if total else 0.0,
        }
        for r in rows
    ]
    return {"dimension": dimension, "total_revenue": round(total, 2), "items": items}


def top_products(
    limit: int = 5, start_month: str | None = None, end_month: str | None = None
) -> dict[str, Any]:
    try:
        limit = max(1, min(int(limit), 20))
    except (TypeError, ValueError):
        raise AnalyticsError("limit must be an integer between 1 and 20.") from None
    s, e = _range(start_month, end_month)
    rows = _query(
        "SELECT product AS name, MAX(category) AS category, SUM(revenue) AS revenue, SUM(units) AS units "
        "FROM sales WHERE month >= :s AND month <= :e GROUP BY product ORDER BY revenue DESC, name ASC",
        {"s": s, "e": e},
    )
    total = sum(float(r["revenue"]) for r in rows)
    items = [
        {
            "rank": i + 1,
            "name": r["name"],
            "category": r["category"],
            "revenue": round(float(r["revenue"]), 2),
            "units": int(r["units"]),
            "share_pct": round(float(r["revenue"]) / total * 100, 2) if total else 0.0,
        }
        for i, r in enumerate(rows[:limit])
    ]
    return {"items": items, "total_revenue": round(total, 2)}


def period_comparison(
    dimension: str,
    baseline_start: str,
    baseline_end: str,
    comparison_start: str,
    comparison_end: str,
) -> dict[str, Any]:
    """Compare average *monthly* revenue between two windows, broken down by a dimension."""
    col = _dimension(dimension)
    bs, be = _month(baseline_start), _month(baseline_end)
    cs, ce = _month(comparison_start), _month(comparison_end)
    if bs > be or cs > ce:
        raise AnalyticsError("A window's start must not be after its end.")
    if not (be < cs or ce < bs):
        raise AnalyticsError("Baseline and comparison windows must not overlap.")

    def month_count(a: str, b: str) -> int:
        n = _query(
            "SELECT COUNT(DISTINCT month) AS n FROM sales WHERE month >= :a AND month <= :b", {"a": a, "b": b}
        )[0]["n"]
        if not n:
            raise AnalyticsError(f"No sales data between {a} and {b}.")
        return int(n)

    n_base, n_comp = month_count(bs, be), month_count(cs, ce)
    rows = _query(
        f"SELECT {col} AS name, "
        "SUM(CASE WHEN month >= :bs AND month <= :be THEN revenue ELSE 0 END) AS base_rev, "
        "SUM(CASE WHEN month >= :cs AND month <= :ce THEN revenue ELSE 0 END) AS comp_rev "
        f"FROM sales WHERE (month >= :bs AND month <= :be) OR (month >= :cs AND month <= :ce) GROUP BY {col}",
        {"bs": bs, "be": be, "cs": cs, "ce": ce},
    )
    base_total = sum(float(r["base_rev"]) for r in rows) / n_base
    comp_total = sum(float(r["comp_rev"]) for r in rows) / n_comp
    total_change = comp_total - base_total

    items = []
    for r in rows:
        base_avg = float(r["base_rev"]) / n_base
        comp_avg = float(r["comp_rev"]) / n_comp
        change = comp_avg - base_avg
        items.append(
            {
                "name": r["name"],
                "baseline_avg_monthly": round(base_avg, 2),
                "comparison_avg_monthly": round(comp_avg, 2),
                "change": round(change, 2),
                "pct_change": round(change / base_avg * 100, 2) if base_avg else None,
                "share_of_total_change_pct": round(change / total_change * 100, 2) if total_change else None,
            }
        )
    items.sort(key=lambda x: (x["change"], x["name"]))  # largest decline first
    return {
        "dimension": dimension,
        "baseline": {"start": bs, "end": be, "months": n_base},
        "comparison": {"start": cs, "end": ce, "months": n_comp},
        "totals": {
            "baseline_avg_monthly": round(base_total, 2),
            "comparison_avg_monthly": round(comp_total, 2),
            "change": round(total_change, 2),
            "pct_change": round(total_change / base_total * 100, 2) if base_total else None,
        },
        "rows": items,
    }


def calculate_kpis(start_month: str | None = None, end_month: str | None = None) -> dict[str, Any]:
    s, e = _range(start_month, end_month)
    summary = sales_summary(start_month, end_month)
    months = summary["months"]
    if not months:
        raise AnalyticsError("No sales data in the requested range.")
    gross = float(
        _query(
            "SELECT COALESCE(SUM(units * unit_price), 0) AS gross FROM sales WHERE month >= :s AND month <= :e",
            {"s": s, "e": e},
        )[0]["gross"]
    )
    net, units = summary["total_revenue"], summary["total_units"]

    mom = []
    for prev, cur in zip(months, months[1:]):
        pct = (cur["revenue"] - prev["revenue"]) / prev["revenue"] * 100 if prev["revenue"] else 0.0
        mom.append({"month": cur["month"], "pct_change": round(pct, 2), "revenue": cur["revenue"]})

    peak, worst_drawdown, drawdown = months[0], 0.0, None
    for m in months:
        if m["revenue"] > peak["revenue"]:
            peak = m
        dd = (m["revenue"] - peak["revenue"]) / peak["revenue"] * 100
        if dd < worst_drawdown:
            worst_drawdown = dd
            drawdown = {"peak_month": peak["month"], "trough_month": m["month"], "pct": round(dd, 2)}

    return {
        "first_month": months[0]["month"],
        "last_month": months[-1]["month"],
        "total_revenue": net,
        "total_units": units,
        "avg_selling_price": round(net / units, 2) if units else 0.0,
        "weighted_avg_discount_pct": round((gross - net) / gross * 100, 2) if gross else 0.0,
        "best_month": max(months, key=lambda m: m["revenue"]),
        "worst_month": min(months, key=lambda m: m["revenue"]),
        "largest_mom_decline": min(mom, key=lambda m: m["pct_change"]) if mom else None,
        "max_drawdown": drawdown,
        "mom_growth": mom,
    }


def run_readonly_query(sql: str) -> dict[str, Any]:
    """Ad-hoc SELECT against approved tables. Not granted to any agent by default."""
    cleaned = validate_readonly_sql(sql, ALLOWED_TABLES)
    wrapped = f"SELECT * FROM ({cleaned}) AS q LIMIT {MAX_ROWS + 1}"
    with get_analytics_readonly_engine().connect() as conn:
        result = conn.execute(text(wrapped))
        columns = list(result.keys())
        rows = [[_json(v) for v in row] for row in result.fetchall()]
    truncated = len(rows) > MAX_ROWS
    return {"columns": columns, "rows": rows[:MAX_ROWS], "row_count": min(len(rows), MAX_ROWS), "truncated": truncated}
