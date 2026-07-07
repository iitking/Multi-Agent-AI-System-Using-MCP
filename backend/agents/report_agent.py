"""Report agent: builds and stores the final report through the Document MCP server."""
from __future__ import annotations

from typing import Any

from backend.agents.common import event, make_result, tool_context
from backend.graph.state import WorkflowState
from backend.mcp_client import ToolCallError, call_tool
from backend.services.audit import now_iso
from backend.services.formatting import fmt_money


def build_sections(state: WorkflowState) -> list[dict[str, Any]]:
    insight = state["insight_result"]
    data = state["data_result"]["data"]
    review = state["review_result"]
    findings = insight["findings"]
    plan = state.get("plan", {})
    intents = plan.get("intents", [])

    sections: list[dict[str, Any]] = [
        {"heading": "Executive summary", "body": insight["summary"]},
        {"heading": "Key findings", "bullets": [f"**{f['id']}** {f['statement']}" for f in findings]},
    ]

    # Top products table
    top = data.get("top_products")
    if top and top.get("items"):
        sections.append({
            "heading": "Top products by revenue",
            "table": {"columns": ["Rank", "Product", "Category", "Revenue", "Share"],
                      "rows": [[i["rank"], i["name"], i["category"], fmt_money(i["revenue"]), f"{i['share_pct']:.1f}%"]
                               for i in top["items"]]},
        })

    # Regional performance table
    by_region = data.get("by_region")
    if by_region and by_region.get("items") and ("region_focus" in intents or plan.get("entities", {}).get("regions")):
        sections.append({
            "heading": "Regional sales performance",
            "table": {"columns": ["Region", "Revenue", "Units Sold", "Share"],
                      "rows": [[r["name"], fmt_money(r["revenue"]), f"{r['units']:,}", f"{r['share_pct']:.1f}%"]
                               for r in by_region["items"]]},
        })

    # Category performance table
    by_category = data.get("by_category")
    if by_category and by_category.get("items") and ("category_focus" in intents or plan.get("entities", {}).get("categories")):
        sections.append({
            "heading": "Category breakdown",
            "table": {"columns": ["Category", "Revenue", "Units Sold", "Share"],
                      "rows": [[c["name"], fmt_money(c["revenue"]), f"{c['units']:,}", f"{c['share_pct']:.1f}%"]
                               for c in by_category["items"]]},
        })

    if insight["hypotheses"]:
        sections.append({
            "heading": "Possible context (hypotheses, not verified facts)",
            "bullets": [f"{h['text']} _(source: {h['source']})_" for h in insight["hypotheses"]],
        })
    if insight["recommendations"]:
        sections.append({
            "heading": "Recommendations",
            "bullets": [f"{r['text']} _(based on {', '.join(r['based_on'])})_" for r in insight["recommendations"]],
        })
    sections.append({
        "heading": "Verification",
        "body": f"Reviewer result: {'PASSED' if review['passed'] else 'FAILED'}.",
        "table": {"columns": ["Check", "Result", "Detail"],
                  "rows": [[c["name"], "pass" if c["passed"] else "FAIL", c["detail"]] for c in review["checks"]]},
    })
    flagged = (state.get("research_result") or {}).get("flagged_sources", [])
    if flagged:
        sections.append({"heading": "Security notes",
                         "bullets": [f"Document '{s}' was withheld: it matched prompt-injection heuristics." for s in flagged]})
    return sections


def get_report_title(state: WorkflowState) -> str:
    plan = state.get("plan") or {}
    intents = plan.get("intents", [])
    if "concept_inquiry" in intents or plan.get("unrecognized_concept"):
        concept = (plan.get("unrecognized_concept") or "Concept").title()
        return f"Enterprise Query Analysis: {concept}"
    if "revenue_drop" in intents:
        return "Revenue Drop & Root Cause Analysis Report"
    if "top_products" in intents:
        return "Top-Performing Products & Sales Analysis Report"
    if "region_focus" in intents:
        return "Regional Sales Performance Report"
    if "category_focus" in intents:
        return "Category Performance & Portfolio Report"
    return "Sales Performance & Intelligence Report"


async def run(state: WorkflowState) -> dict[str, Any]:
    ctx = tool_context(state, "report_agent")
    action = state.get("external_action")
    title = get_report_title(state)
    try:
        created = await call_tool(ctx, "document", "create_report", {
            "title": title,
            "sections": build_sections(state),
            "metadata": {"run": state["run_id"], "generated": now_iso(),
                         "tool_calls": len(state.get("tool_calls", [])) + len(ctx.calls)},
        })
        markdown = created["markdown"]
        saved = await call_tool(ctx, "document", "save_report", {"run_id": state["run_id"], "markdown": markdown})
    except ToolCallError as exc:
        message = f"Report generation failed: {exc}"[:300]
        return {"report": make_result("report_agent", "error", errors=[message]), "tool_calls": ctx.calls,
                "errors": [message], "status": "failed", "events": [event("report_agent", message, "error")]}

    report = make_result("report_agent", findings=["Report generated and stored."], next_action=(
        "await_human_approval" if action else "complete"), markdown=markdown, path=saved["path"])
    return {
        "report": report,
        "tool_calls": ctx.calls,
        "status": "report_ready",
        "events": [event("report_agent", f"Saved report to {saved['path']}"
                         + ("; external action awaits human approval" if action else ""))],
    }
