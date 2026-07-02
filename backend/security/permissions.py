"""Authorization rules: which agent may call which MCP tool, and what each user role may do.

These rules are enforced in code (the MCP client and the API) - never only in prompts.
"""
from __future__ import annotations

# agent -> MCP server -> allowed tool names.
# Note: `run_readonly_query` exists on the data server but is deliberately NOT granted to any agent.
AGENT_TOOL_ALLOWLIST: dict[str, dict[str, frozenset[str]]] = {
    "data_analyst": {
        "data": frozenset(
            {"get_sales_summary", "revenue_by_dimension", "top_products", "period_comparison", "calculate_kpis"}
        )
    },
    "researcher": {"research": frozenset({"search_company_docs", "list_company_docs"})},
    "reviewer": {
        "data": frozenset({"get_sales_summary", "revenue_by_dimension", "top_products", "period_comparison", "calculate_kpis"})
    },
    "report_agent": {"document": frozenset({"create_report", "save_report"})},
}

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "viewer": frozenset({"runs:read"}),
    "analyst": frozenset({"runs:read", "runs:create", "metrics:read", "tools:read"}),
    "admin": frozenset(
        {"runs:read", "runs:create", "runs:approve", "metrics:read", "tools:read", "audit:read"}
    ),
}


class PermissionDenied(Exception):
    """Raised when an agent or user attempts something outside its allowlist."""


def assert_tool_allowed(agent: str, server: str, tool: str) -> None:
    allowed = AGENT_TOOL_ALLOWLIST.get(agent, {}).get(server, frozenset())
    if tool not in allowed:
        raise PermissionDenied(f"agent '{agent}' may not call {server}.{tool}")


def has_permission(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())
