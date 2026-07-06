"""Planner / Supervisor agent: turns a business request into a structured plan.

The planner decides *what* to analyse. It can never grant tools: the per-agent tool allowlist is
enforced in code (see backend/security/permissions.py), whatever the plan says.
"""
from __future__ import annotations

import re
from typing import Any

from backend.agents.common import event, make_result
from backend.graph.state import WorkflowState
from backend.security.guard import scan_untrusted
from backend.security.permissions import AGENT_TOOL_ALLOWLIST
from backend.services.llm import llm_available, llm_json

INTENTS = ("revenue_drop", "top_products", "trend", "kpi", "region_focus", "category_focus", "product_focus", "concept_inquiry")

BUSINESS_TERMS = {
    "sale", "sales", "revenue", "drop", "dropped", "drops", "decline", "declined", "declines",
    "decrease", "decreased", "fell", "fall", "falling", "slump", "loss", "lost", "dip", "growth",
    "unit", "units", "asp", "price", "pricing", "kpi", "kpis", "margin", "margins", "profit",
    "bestseller", "bestsellers", "bestselling", "performance", "performer", "performers", "rank",
    "ranking", "quarter", "q1", "q2", "q3", "q4", "month", "monthly", "annual", "overview",
    "summary", "totals", "trend", "trends", "discount", "discounts", "drawdown", "seasonality",
    "mom", "yoy", "dimension", "dimensions", "breakdown", "analysis", "analyze", "analytics",
    "region", "regions", "product", "products", "category", "categories", "financial", "market",
    "inventory", "distribution", "incident", "policy", "guidelines", "order", "orders", "customer",
    "customers", "outage", "disruption", "memo", "report"
}

_INTENT_KEYWORDS: dict[str, list[str]] = {
    "revenue_drop": [
        "drop", "dropped", "drops", "decline", "declined", "declines", "decrease", "decreased",
        "fell", "fall", "falling", "slump", "dip", "dipped", "down", "loss", "lost", "problem", "issue", "why"
    ],
    "top_products": [
        "top product", "top products", "top-performing", "top performing", "top performer", "top performers",
        "top seller", "top sellers", "top selling", "top-selling", "bestseller", "bestsellers",
        "best-selling", "best selling", "best product", "best products", "highest revenue product",
        "most sold product", "rank products", "ranking products"
    ],
    "region_focus": ["region", "regions", "regional", "territory", "geography", "north", "south", "east", "west"],
    "category_focus": ["category", "categories", "electronics", "wearables", "accessories"],
    "product_focus": [
        "laptop", "aurora", "phone", "nimbus", "tablet", "pulse", "smartwatch", "orbit",
        "headphones", "zephyr", "speaker", "echo", "device", "devices"
    ],
    "trend": ["trend", "trends", "growth", "over time", "by month", "monthly", "seasonal", "seasonality", "quarter", "q1", "q2", "q3", "q4"],
    "kpi": ["total revenue", "average selling price", "average", "avg", "kpi", "kpis", "overview", "summary", "totals", "metrics"],
}

KNOWN_REGIONS = ["North", "South", "East", "West"]
KNOWN_PRODUCTS = [
    "Aurora Laptop", "Nimbus Phone", "Pulse Tablet",
    "Orbit Smartwatch", "Zephyr Headphones", "Echo Speaker"
]
KNOWN_CATEGORIES = ["Electronics", "Wearables", "Accessories"]

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

_DEFAULT_QUERIES = {
    "revenue_drop": ["revenue decline causes", "supply chain fulfilment disruption", "pricing promotion discount change", "competitor launch market share"],
    "top_products": ["product pricing promotion market performance"],
    "region_focus": ["regional distribution fulfillment delivery performance"],
    "category_focus": ["category growth demand margins"],
    "product_focus": ["product catalog pricing specification"],
    "trend": ["seasonality holiday demand timeline"],
    "kpi": ["pricing promotion discount annual performance"],
}


def _has_keyword(text: str, keyword: str) -> bool:
    return re.search(rf"(?<![a-z]){re.escape(keyword)}(?![a-z])", text) is not None


MONTH_NAMES = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "jun": "06", "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12"
}


def extract_time_period(text: str) -> dict[str, str] | None:
    lowered = text.lower()
    year_match = re.search(r"\b(20\d{2})\b", text)
    year = year_match.group(1) if year_match else None

    ym_match = re.search(r"\b(20\d{2}-(?:0[1-9]|1[0-2]))\b", text)
    if ym_match:
        m = ym_match.group(1)
        return {"year": m[:4], "start_month": m, "end_month": m, "label": m}

    q_match = re.search(r"\bq([1-4])\b", lowered)
    if q_match:
        q = int(q_match.group(1))
        y = year or "2025"
        q_map = {1: ("01", "03"), 2: ("04", "06"), 3: ("07", "09"), 4: ("10", "12")}
        s_m, e_m = q_map[q]
        return {"year": y, "start_month": f"{y}-{s_m}", "end_month": f"{y}-{e_m}", "label": f"{y} Q{q}"}

    for m_name, m_num in MONTH_NAMES.items():
        if re.search(rf"\b{m_name}\b", lowered):
            y = year or "2025"
            return {"year": y, "start_month": f"{y}-{m_num}", "end_month": f"{y}-{m_num}", "label": f"{m_name.capitalize()} {y}"}

    if year:
        return {"year": year, "start_month": f"{year}-01", "end_month": f"{year}-12", "label": year}

    return None


def extract_entities(request: str) -> dict[str, list[str]]:
    lowered = request.lower()
    regions = [r for r in KNOWN_REGIONS if r.lower() in lowered]
    products = [p for p in KNOWN_PRODUCTS if any(part.lower() in lowered for part in p.split())]
    categories = [c for c in KNOWN_CATEGORIES if c.lower() in lowered]
    return {
        "regions": regions,
        "products": products,
        "categories": categories,
    }


def extract_concept_subject(text: str) -> str:
    cleaned = re.sub(r"[?!.,;]+$", "", text.strip())
    match = re.search(
        r"^(?:what\s+(?:is|are|was|were)|who\s+is|tell\s+me\s+about|explain|define|meaning\s+of)\s+(?:the\s+|a\s+|an\s+)?(.+)",
        cleaned,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    hindi_match = re.search(r"^(.+?)\s+(?:kya\s+hai|kya\s+hota\s+hai|ka\s+matlab)", cleaned, re.IGNORECASE)
    if hindi_match:
        return hindi_match.group(1).strip()
    return cleaned


def is_business_or_analytics_query(request: str) -> bool:
    lowered = request.lower()
    if scan_untrusted(request):
        return True
    if extract_time_period(request):
        return True
    words = set(re.findall(r"[a-z0-9]+", lowered))
    if words & BUSINESS_TERMS:
        return True
    if any(r.lower() in lowered for r in KNOWN_REGIONS):
        return True
    if any(c.lower() in lowered for c in KNOWN_CATEGORIES):
        return True
    if any(any(part.lower() in lowered for part in p.split()) for p in KNOWN_PRODUCTS):
        return True
    return False


def classify_intents(request: str) -> list[str]:
    lowered = request.lower()
    intents = [i for i, words in _INTENT_KEYWORDS.items() if any(_has_keyword(lowered, w) for w in words)]
    if intents:
        return intents
    if not is_business_or_analytics_query(request):
        return ["concept_inquiry"]
    return ["kpi", "trend"]


def detect_external_action(request: str) -> dict[str, Any] | None:
    lowered = request.lower()
    email = _EMAIL_RE.search(request)
    if email or re.search(r"\be-?mail\b", lowered):
        return {"type": "email", "recipient": email.group(0).lower() if email else None,
                "subject": "Sales analysis report", "status": "pending_approval"}
    if re.search(r"\bslack\b", lowered):
        return {"type": "slack", "recipient": None, "subject": "Sales analysis report", "status": "pending_approval"}
    return None


def build_plan(
    request: str,
    intents: list[str],
    queries: list[str],
    entities: dict[str, list[str]] | None = None,
    time_period: dict[str, str] | None = None,
    unrecognized_concept: str | None = None,
) -> dict[str, Any]:
    allow = {agent: [f"{s}.{t}" for s, tools in servers.items() for t in sorted(tools)]
             for agent, servers in AGENT_TOOL_ALLOWLIST.items()}
    tasks = [
        {"id": "t1", "agent": "data_analyst", "depends_on": [], "tools": allow["data_analyst"],
         "description": "Query monthly revenue, KPIs, period comparisons and top products." if not unrecognized_concept else f"Check database records for '{unrecognized_concept}'."},
        {"id": "t2", "agent": "researcher", "depends_on": [], "tools": allow["researcher"],
         "description": "Retrieve approved company context that may explain the numbers." if not unrecognized_concept else f"Search company documents for '{unrecognized_concept}'."},
        {"id": "t3", "agent": "insight", "depends_on": ["t1", "t2"], "tools": [],
         "description": "Interpret evidence; produce verifiable findings and recommendations."},
        {"id": "t4", "agent": "reviewer", "depends_on": ["t3"], "tools": allow["reviewer"],
         "description": "Re-verify figures against the data and check evidence and completeness."},
        {"id": "t5", "agent": "report_agent", "depends_on": ["t4"], "tools": allow["report_agent"],
         "description": "Generate and store the final report."},
    ]
    return {
        "intents": intents,
        "entities": entities or {"regions": [], "products": [], "categories": []},
        "time_period": time_period,
        "unrecognized_concept": unrecognized_concept,
        "dimensions": ["region", "product", "category"],
        "research_queries": queries[:4],
        "external_action": detect_external_action(request),
        "request_flags": scan_untrusted(request),
        "tasks": tasks,
    }


async def run(state: WorkflowState) -> dict[str, Any]:
    request = state["request"]
    intents = classify_intents(request)
    entities = extract_entities(request)
    time_period = extract_time_period(request)

    unrecognized_concept = None
    if "concept_inquiry" in intents:
        unrecognized_concept = extract_concept_subject(request)

    queries: list[str] = []
    if unrecognized_concept:
        queries.append(unrecognized_concept)

    for prod in entities.get("products", []):
        if prod not in queries:
            queries.append(prod)

    for intent in intents:
        if intent in _DEFAULT_QUERIES:
            queries += [q for q in _DEFAULT_QUERIES[intent] if q not in queries]

    planner, usage = "rule-based", []

    if llm_available():
        data, used = await llm_json(
            "You are a planning agent for a business-analytics system. Reply with JSON only: "
            '{"intents": [subset of ' + str(list(INTENTS)) + '], "research_queries": [up to 3 short search phrases]}.',
            f"Business request: {request}",
            "planner",
        )
        if used:
            usage.append(used)
        if data and isinstance(data.get("intents"), list):
            llm_intents = [i for i in data["intents"] if i in INTENTS]
            if llm_intents:
                intents = list(dict.fromkeys(intents + llm_intents))
                planner = "llm+rules"
            extra = [q for q in data.get("research_queries", []) if isinstance(q, str) and re.fullmatch(r"[A-Za-z0-9 ,'\-]{3,80}", q)]
            queries += [q for q in extra[:3] if q not in queries]

    plan = build_plan(request, intents, queries, entities, time_period, unrecognized_concept)
    plan["planner"] = planner
    flags = plan["request_flags"]
    result = make_result(
        "planner",
        findings=[f"Intents: {', '.join(intents)}"],
        next_action="data_analyst,researcher",
        errors=[f"Request matched injection heuristics: {', '.join(flags)} (treated as plain text)"] if flags else [],
    )
    return {
        "plan": plan,
        "external_action": plan["external_action"],
        "events": [event("planner", f"Planned {len(plan['tasks'])} tasks for intents: {', '.join(intents)}")],
        "llm_usage": usage,
        "errors": result["errors"],
        "status": "planned",
    }
