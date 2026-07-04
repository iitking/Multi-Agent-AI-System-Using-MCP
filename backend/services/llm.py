"""Optional LLM access. Every agent has a deterministic fallback, so the system runs without a key.

LangChain model calls are traced by LangSmith automatically when LANGSMITH_TRACING=true.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from backend.config import get_settings

log = logging.getLogger("llm")


def llm_available() -> bool:
    return bool(get_settings().openai_api_key)


def _parse_json(text: str) -> dict[str, Any] | None:
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


async def llm_json(system: str, user: str, agent: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Ask the model for a JSON object. Returns ``(data, usage)``; ``(None, None)`` on any failure."""
    settings = get_settings()
    if not settings.openai_api_key:
        return None, None
    try:
        from langchain_openai import ChatOpenAI

        model = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=0,
            timeout=30,
            max_retries=1,
        )
        response = await model.ainvoke([("system", system), ("human", user)])
        content = response.content if isinstance(response.content, str) else json.dumps(response.content)
        usage_meta = getattr(response, "usage_metadata", None) or {}
        tokens_in, tokens_out = int(usage_meta.get("input_tokens", 0)), int(usage_meta.get("output_tokens", 0))
        usage = {
            "agent": agent,
            "input_tokens": tokens_in,
            "output_tokens": tokens_out,
            "cost_usd": round(
                tokens_in / 1000 * settings.llm_price_in_per_1k + tokens_out / 1000 * settings.llm_price_out_per_1k, 6
            ),
        }
        return _parse_json(content), usage
    except Exception as exc:  # network, auth, quota... fall back to deterministic logic
        log.warning("LLM call failed for %s: %s", agent, type(exc).__name__)
        return None, None
