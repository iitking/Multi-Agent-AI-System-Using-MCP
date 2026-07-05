"""Document MCP server - assemble and store reports.

Run standalone (stdio):  python -m backend.mcp_servers.document_server
"""
from typing import Any

from mcp.server.fastmcp import FastMCP

from backend.services import documents

mcp = FastMCP("report-documents")


@mcp.tool()
def create_report(title: str, sections: list[dict[str, Any]], metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a Markdown report. Each section may have 'heading', 'body', 'bullets' and 'table' {columns, rows}."""
    return {"markdown": documents.build_markdown(title, sections, metadata)}


@mcp.tool()
def save_report(run_id: str, markdown: str) -> dict[str, Any]:
    """Store a report as reports/<run_id>.md and return its relative path."""
    return documents.save_markdown(run_id, markdown)


if __name__ == "__main__":
    mcp.run()
