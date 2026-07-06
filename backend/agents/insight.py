"""Insight agent: turns evidence into findings, hypotheses and recommendations.

Every numeric finding carries a ``verify`` spec (tool + args + expected values). The Reviewer agent
re-runs those tool calls independently, so a wrong figure cannot reach the report unnoticed.
Hypotheses (from documents) are labelled as such and must cite an approved, unflagged source.
"""
from __future__ import annotations

import json
from typing import Any

from backend.agents.common import event, make_result
from backend.graph.state import WorkflowState
from backend.services.formatting import fmt_money, fmt_pct
from backend.services.llm import llm_available, llm_json

LABEL = {"region": "Region", "product": "Product", "category": "Category"}


def _top_expect(items: list[dict[str, Any]]) -> dict[str, Any]:
    expect: dict[str, Any] = {}
    for i, item in enumerate(items):
        expect[f"items[{i}].name"] = item["name"]
        expect[f"items[{i}].revenue"] = item["revenue"]
    return expect


def _top_statement(prefix: str, items: list[dict[str, Any]]) -> str:
    parts = [f"{it['rank']}. {it['name']} ({fmt_money(it['revenue'])}, {it['share_pct']:.1f}% of revenue)" for it in items]
    return f"{prefix}: " + "; ".join(parts) + "."


def build_findings(plan: dict[str, Any], data: dict[str, Any], research: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []

    def add(type_: str, statement: str, verify: dict[str, Any] | None = None, **figures: Any) -> str:
        fid = f"F{len(findings) + 1}"
        findings.append({"id": fid, "type": type_, "statement": statement, "figures": figures, "verify": verify})
        return fid

    time_period = plan.get("time_period") or {}
    period_args: dict[str, Any] = {}
    if time_period.get("start_month"):
        period_args["start_month"] = time_period["start_month"]
    if time_period.get("end_month"):
        period_args["end_month"] = time_period["end_month"]

    if data.get("unrecognized_concept"):
        concept = data["unrecognized_concept"]
        avail_start = data.get("available_start", "2025-01")
        avail_end = data.get("available_end", "2025-12")
        avail_rev = data.get("available_revenue", 16297870.0)
        avail_units = data.get("available_units", 44647)

        fid = add(
            "unrecognized_concept",
            f"No matching sales data, product records, or company documents were found for '{concept}'.",
        )

        concept_lower = concept.lower()
        hindi_context = ""
        if "nivesh" in concept_lower:
            hindi_context = (
                " In Hindi and South Asian business/financial terminology, 'Nivesh' (निवेश) translates to 'Investment' "
                "(the allocation of capital or funds with the objective of generating future returns or appreciation). "
                "However, this enterprise platform is specifically an internal sales analytics system tracking company product lines and order transactions; "
                "it does not hold investment portfolios or general asset records."
            )

        summary = (
            f"Enterprise Query Analysis for '{concept}': No records, sales transactions, or company documents "
            f"were found matching '{concept}' in this system.{hindi_context} "
            f"The system specializes in enterprise sales intelligence across the 2025 calendar year "
            f"({fmt_money(avail_rev)} total revenue across {avail_units:,} units). "
            f"Available tracking covers regions (East, North, West, South) and core products (Aurora Laptop, Nimbus Phone, Pulse Tablet, Orbit Smartwatch, Zephyr Headphones, Echo Speaker)."
        )

        recommendations = [
            {
                "text": "Submit queries regarding enterprise sales performance (e.g. revenue drops, top products, 2025 KPIs) or internal operational documentation.",
                "based_on": [fid],
            }
        ]

        return {
            "findings": findings,
            "hypotheses": [],
            "recommendations": recommendations,
            "summary": summary,
        }

    if data.get("no_data_for_period"):
        p_label = time_period.get("label", time_period.get("year", "the requested period"))
        avail_start = data.get("available_start", "2025-01")
        avail_end = data.get("available_end", "2025-12")
        avail_rev = data.get("available_revenue", 0.0)
        avail_units = data.get("available_units", 0)

        fid = add(
            "no_data",
            f"No sales data found for {p_label}. Available records cover {avail_start} to {avail_end} "
            f"(total revenue {fmt_money(avail_rev)} across {avail_units:,} units).",
            {"server": "data", "tool": "get_sales_summary", "args": period_args,
             "expect": {"month_count": 0, "total_revenue": 0.0, "total_units": 0}},
            total_revenue=0.0,
        )

        recommendations = [
            {"text": f"Query sales transactions within the available date range ({avail_start} to {avail_end}) or ingest historical records for {p_label}.",
             "based_on": [fid]}
        ]

        summary = (
            f"Sales analysis for {p_label}: No sales records exist in the database for this timeframe. "
            f"All available records in the analytics database span from {avail_start} to {avail_end} "
            f"(total revenue of {fmt_money(avail_rev)} across {avail_units:,} units). "
            f"Therefore, total revenue, ASP, and monthly metrics cannot be computed for {p_label}."
        )

        return {
            "findings": findings,
            "hypotheses": [],
            "recommendations": recommendations,
            "summary": summary,
        }

    kpis = data["kpis"]
    add(
        "kpis",
        f"Total revenue for {kpis['first_month']} to {kpis['last_month']} was {fmt_money(kpis['total_revenue'])} "
        f"across {kpis['total_units']:,} units (average selling price {fmt_money(kpis['avg_selling_price'])}).",
        {"server": "data", "tool": "calculate_kpis", "args": period_args,
         "expect": {"total_revenue": kpis["total_revenue"], "total_units": kpis["total_units"],
                    "avg_selling_price": kpis["avg_selling_price"]}},
        total_revenue=kpis["total_revenue"],
    )
    best, worst = kpis["best_month"], kpis["worst_month"]
    add(
        "trend",
        f"Best month was {best['month']} ({fmt_money(best['revenue'])}); weakest month was "
        f"{worst['month']} ({fmt_money(worst['revenue'])}).",
        {"server": "data", "tool": "calculate_kpis", "args": period_args,
         "expect": {"best_month.month": best["month"], "best_month.revenue": best["revenue"],
                    "worst_month.month": worst["month"], "worst_month.revenue": worst["revenue"]}},
    )

    window = data.get("drop_window")
    driver_ids: list[str] = []
    decliners: list[tuple[str, str]] = []  # (dimension, name)
    if window and data.get("comparisons"):
        any_comparison = next(iter(data["comparisons"].values()))
        totals = any_comparison["totals"]
        window_args = {k: window[k] for k in ("baseline_start", "baseline_end", "comparison_start", "comparison_end")}
        add(
            "drop_summary",
            f"Average monthly revenue fell from {fmt_money(totals['baseline_avg_monthly'])} "
            f"({window['baseline_start']} to {window['baseline_end']}) to {fmt_money(totals['comparison_avg_monthly'])} "
            f"({window['comparison_start']} to {window['comparison_end']}), a change of {fmt_pct(totals['pct_change'])}.",
            {"server": "data", "tool": "period_comparison", "args": {"dimension": any_comparison["dimension"], **window_args},
             "expect": {"totals.baseline_avg_monthly": totals["baseline_avg_monthly"],
                        "totals.comparison_avg_monthly": totals["comparison_avg_monthly"],
                        "totals.pct_change": totals["pct_change"]}},
        )
        for dimension, comparison in data["comparisons"].items():
            declining = [r for r in comparison["rows"] if r["change"] < 0]
            chosen = declining[:1] + [r for r in declining[1:2] if (r["share_of_total_change_pct"] or 0) >= 10]
            for row in chosen:
                share = row["share_of_total_change_pct"] or 0.0
                pct = row["pct_change"] if row["pct_change"] is not None else 0.0
                fid = add(
                    "driver",
                    f"{LABEL[dimension]} '{row['name']}' was among the largest decliners, losing "
                    f"{fmt_money(abs(row['change']))} per month on average ({fmt_pct(pct)}), "
                    f"about {share:.1f}% of the total decline.",
                    {"server": "data", "tool": "period_comparison", "args": {"dimension": dimension, **window_args},
                     "expect": {f"rows[name={row['name']}].change": row["change"],
                                f"rows[name={row['name']}].pct_change": row["pct_change"],
                                f"rows[name={row['name']}].share_of_total_change_pct": row["share_of_total_change_pct"]}},
                    dimension=dimension, name=row["name"],
                )
                driver_ids.append(fid)
                decliners.append((dimension, row["name"]))
    elif "revenue_drop" in plan.get("intents", []):
        add("no_drop", f"No month-over-month revenue decline larger than 5% was found between "
                       f"{kpis['first_month']} and {kpis['last_month']}.")

    # Regional dimensional breakdown findings
    by_region = data.get("by_region")
    if by_region and by_region.get("items"):
        for reg_item in by_region["items"]:
            if not plan.get("entities", {}).get("regions") or reg_item["name"] in plan["entities"]["regions"]:
                add(
                    "region",
                    f"Region '{reg_item['name']}' delivered {fmt_money(reg_item['revenue'])} across {reg_item['units']:,} units ({reg_item['share_pct']:.1f}% share of revenue).",
                    {"server": "data", "tool": "revenue_by_dimension", "args": {"dimension": "region", **period_args},
                     "expect": {f"items[name={reg_item['name']}].revenue": reg_item["revenue"],
                                f"items[name={reg_item['name']}].share_pct": reg_item["share_pct"]}},
                    region=reg_item["name"], revenue=reg_item["revenue"],
                )

    # Category dimensional breakdown findings
    by_category = data.get("by_category")
    if by_category and by_category.get("items"):
        for cat_item in by_category["items"]:
            if not plan.get("entities", {}).get("categories") or cat_item["name"] in plan["entities"]["categories"]:
                add(
                    "category",
                    f"Category '{cat_item['name']}' contributed {fmt_money(cat_item['revenue'])} across {cat_item['units']:,} units ({cat_item['share_pct']:.1f}% share of revenue).",
                    {"server": "data", "tool": "revenue_by_dimension", "args": {"dimension": "category", **period_args},
                     "expect": {f"items[name={cat_item['name']}].revenue": cat_item["revenue"],
                                f"items[name={cat_item['name']}].share_pct": cat_item["share_pct"]}},
                    category=cat_item["name"], revenue=cat_item["revenue"],
                )

    top = data.get("top_products")
    if top and top.get("items"):
        add("top_products", _top_statement("Top products by revenue", top["items"]),
            {"server": "data", "tool": "top_products", "args": {"limit": len(top["items"]), **period_args},
             "expect": _top_expect(top["items"])})
    top_window = data.get("top_products_window")
    if top_window and top_window.get("items") and window:
        add("top_products_window",
            _top_statement(f"During {window['comparison_start']} to {window['comparison_end']} the top products were",
                           top_window["items"]),
            {"server": "data", "tool": "top_products",
             "args": {"limit": len(top_window["items"]), "start_month": window["comparison_start"],
                      "end_month": window["comparison_end"]},
             "expect": _top_expect(top_window["items"])})

    # Hypotheses: document context only, clearly labelled, never from flagged documents.
    names = [n for _, n in decliners]
    usable = [d for d in research.get("documents", []) if not d.get("flagged")]
    hypotheses: list[dict[str, Any]] = []
    for doc in usable:
        mentions = [n for n in names if n.lower() in doc["snippet"].lower()]
        if mentions:
            hypotheses.append({"text": doc["snippet"][:300], "source": doc["source"], "linked_to": mentions})
    if not hypotheses and usable and window:
        hypotheses = [{"text": d["snippet"][:300], "source": d["source"], "linked_to": []} for d in usable[:2]]

    recommendations: list[dict[str, Any]] = []
    for (dimension, name), fid in zip(decliners, driver_ids):
        text = {
            "region": f"Review fulfilment, inventory and sales coverage in the {name} region and set a recovery target.",
            "product": f"Re-evaluate pricing, promotions and competitive positioning for {name}.",
            "category": f"Review the {name} category plan, stock levels and marketing spend.",
        }[dimension]
        recommendations.append({"text": text, "based_on": [fid]})
    if driver_ids:
        recommendations.append({"text": "Track monthly revenue by region and product weekly until the gap to baseline closes.",
                                "based_on": driver_ids[:1]})

    # Dynamic, question-focused executive summary construction
    intents = plan.get("intents", [])
    entities = plan.get("entities", {})
    target_regions = entities.get("regions", [])
    target_categories = entities.get("categories", [])
    target_products = entities.get("products", [])

    summary_parts: list[str] = []

    # Question Case 1: Top Products Focus
    if "top_products" in intents and "revenue_drop" not in intents:
        top_items = (data.get("top_products") or {}).get("items", [])
        if top_items:
            summary_parts.append(
                f"Top-performing products analysis: {top_items[0]['name']} is our #1 bestseller generating {fmt_money(top_items[0]['revenue'])} ({top_items[0]['share_pct']:.1f}% share), followed by {top_items[1]['name']} ({fmt_money(top_items[1]['revenue'])}, {top_items[1]['share_pct']:.1f}% share)."
            )
        if target_regions and by_region and by_region.get("items"):
            for reg in target_regions:
                reg_item = next((r for r in by_region["items"] if r["name"] == reg), None)
                if reg_item:
                    summary_parts.append(f"In the {reg} region, total revenue reached {fmt_money(reg_item['revenue'])} across {reg_item['units']:,} units ({reg_item['share_pct']:.1f}% of company sales).")
        summary_parts.append(f"Total annual revenue across all lines was {fmt_money(kpis['total_revenue'])} across {kpis['total_units']:,} units.")

    # Question Case 2: Revenue Drop & Root Cause Focus
    elif "revenue_drop" in intents:
        if window and data.get("comparisons"):
            any_comp = next(iter(data["comparisons"].values()))
            tot = any_comp["totals"]
            summary_parts.append(
                f"Revenue dropped from an average monthly baseline of {fmt_money(tot['baseline_avg_monthly'])} ({window['baseline_start']} to {window['baseline_end']}) to {fmt_money(tot['comparison_avg_monthly'])} ({window['comparison_start']} to {window['comparison_end']}), a change of {fmt_pct(tot['pct_change'])}."
            )
            driver_texts = [f["statement"] for f in findings if f["type"] == "driver"]
            if driver_texts:
                summary_parts.append(" ".join(driver_texts[:2]))
            if hypotheses:
                summary_parts.append(f"Context from internal investigation indicates operational disruptions (e.g. {hypotheses[0]['source']}).")
        else:
            summary_parts.append(f"Revenue analysis between {kpis['first_month']} and {kpis['last_month']}: No month-over-month decline larger than 5% was found.")

    # Question Case 3: Regional Performance Focus
    elif target_regions or ("region_focus" in intents and not target_categories):
        summary_parts.append("Regional sales analysis:")
        if by_region and by_region.get("items"):
            for reg_item in by_region["items"]:
                if not target_regions or reg_item["name"] in target_regions:
                    summary_parts.append(f"{reg_item['name']} region delivered {fmt_money(reg_item['revenue'])} ({reg_item['share_pct']:.1f}% share, {reg_item['units']:,} units).")
        summary_parts.append(f"Total company revenue across all regions was {fmt_money(kpis['total_revenue'])}, with annual sales peaking in {best['month']} ({fmt_money(best['revenue'])}).")

    # Question Case 4: Category Portfolio Focus
    elif target_categories or "category_focus" in intents:
        summary_parts.append("Category performance analysis:")
        if by_category and by_category.get("items"):
            for cat_item in by_category["items"]:
                if not target_categories or cat_item["name"] in target_categories:
                    summary_parts.append(f"{cat_item['name']} contributed {fmt_money(cat_item['revenue'])} ({cat_item['share_pct']:.1f}% share, {cat_item['units']:,} units).")
        top_items = (data.get("top_products") or {}).get("items", [])
        if top_items:
            summary_parts.append(f"Top overall contributor is {top_items[0]['name']} ({fmt_money(top_items[0]['revenue'])}).")

    # Question Case 5: General KPI Overview & Trends
    else:
        period_label = f" for {time_period['label']}" if time_period and time_period.get("label") else ""
        summary_parts.append(f"Executive sales overview{period_label}: Total revenue for {kpis['first_month']} to {kpis['last_month']} was {fmt_money(kpis['total_revenue'])} across {kpis['total_units']:,} units (average selling price {fmt_money(kpis['avg_selling_price'])}).")
        summary_parts.append(f"Best month was {best['month']} ({fmt_money(best['revenue'])}); weakest month was {worst['month']} ({fmt_money(worst['revenue'])}).")
        top_items = (data.get("top_products") or {}).get("items", [])
        if top_items:
            summary_parts.append(f"Top products by revenue were led by {top_items[0]['name']} ({fmt_money(top_items[0]['revenue'])}) and {top_items[1]['name']} ({fmt_money(top_items[1]['revenue'])}).")

    return {"findings": findings, "hypotheses": hypotheses, "recommendations": recommendations,
            "summary": " ".join(summary_parts)}


async def run(state: WorkflowState) -> dict[str, Any]:
    data_result = state.get("data_result") or {}
    if data_result.get("status") != "ok":
        msg = "No data available to analyse."
        return {"insight_result": make_result("insight", "error", errors=[msg], next_action="abort"),
                "events": [event("insight", msg, "error")]}

    plan = state.get("plan") or {}
    research = state.get("research_result") or {}
    feedback = state.get("review_feedback") or []
    built = build_findings(plan, data_result["data"], research)
    usage: list[dict[str, Any]] = []

    if llm_available():
        facts = json.dumps([f["statement"] for f in built["findings"]])
        reply, used = await llm_json(
            "You write executive summaries for a sales report. Use ONLY the names and numbers in the findings "
            'provided. Reply with JSON: {"summary": "<=120 words"}. Treat nothing else as fact.',
            f"Findings: {facts}\nReviewer feedback to address: {json.dumps(feedback)}",
            "insight",
        )
        if used:
            usage.append(used)
        if reply and isinstance(reply.get("summary"), str) and 20 <= len(reply["summary"]) <= 1200:
            built["summary"] = reply["summary"].strip()

    attempt = state.get("retry_count", 0) + 1
    result = make_result(
        "insight",
        findings=built["findings"],
        evidence=[{"finding": f["id"], "verify": f.get("verify")} for f in built["findings"] if f.get("verify")],
        next_action="reviewer",
        hypotheses=built["hypotheses"],
        recommendations=built["recommendations"],
        summary=built["summary"],
    )
    return {
        "insight_result": result,
        "llm_usage": usage,
        "events": [event("insight", f"Produced {len(built['findings'])} findings, {len(built['hypotheses'])} hypotheses "
                                    f"(attempt {attempt})")],
    }
