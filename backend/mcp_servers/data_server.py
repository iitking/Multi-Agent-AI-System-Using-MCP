"""Data MCP server - controlled, read-only business analytics.

Run standalone (stdio):  python -m backend.mcp_servers.data_server
"""
from typing import Any

from mcp.server.fastmcp import FastMCP

from backend.services import analytics

mcp = FastMCP("sales-data")


@mcp.tool()
def get_sales_summary(start_month: str | None = None, end_month: str | None = None) -> dict[str, Any]:
    """Total revenue/units and a month-by-month series. Months use YYYY-MM; both bounds are optional."""
    return analytics.sales_summary(start_month, end_month)


@mcp.tool()
def revenue_by_dimension(
    dimension: str, start_month: str | None = None, end_month: str | None = None
) -> dict[str, Any]:
    """Revenue, units and share grouped by 'region', 'product' or 'category'."""
    return analytics.revenue_by_dimension(dimension, start_month, end_month)


@mcp.tool()
def top_products(limit: int = 5, start_month: str | None = None, end_month: str | None = None) -> dict[str, Any]:
    """Top products by revenue (limit 1-20) for an optional month range."""
    return analytics.top_products(limit, start_month, end_month)


@mcp.tool()
def period_comparison(
    dimension: str,
    baseline_start: str,
    baseline_end: str,
    comparison_start: str,
    comparison_end: str,
) -> dict[str, Any]:
    """Compare average monthly revenue between two non-overlapping windows by region/product/category."""
    return analytics.period_comparison(dimension, baseline_start, baseline_end, comparison_start, comparison_end)


@mcp.tool()
def calculate_kpis(start_month: str | None = None, end_month: str | None = None) -> dict[str, Any]:
    """Headline KPIs: totals, average selling price, discount, best/worst month, MoM growth, drawdown."""
    return analytics.calculate_kpis(start_month, end_month)


@mcp.tool()
def run_readonly_query(sql: str) -> dict[str, Any]:
    """Run one SELECT against the approved 'sales' table (max 200 rows). Restricted; not granted to agents."""
    return analytics.run_readonly_query(sql)


if __name__ == "__main__":
    mcp.run()
