"""Hand an *approved* action to n8n. Never called without a recorded human approval."""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from backend.config import get_settings
from backend.services.audit import now_iso


async def dispatch_approved_action(run: dict[str, Any], approver: str) -> dict[str, Any]:
    """POST the approved action to the n8n webhook with bounded retries.

    Returns ``{"delivered": bool, "mode": "n8n"|"simulated", "detail": str}``. When no webhook is
    configured the delivery is *simulated* so the full flow can be exercised locally.
    """
    settings = get_settings()
    action = run.get("external_action") or {}
    if not settings.n8n_webhook_url:
        return {"delivered": False, "mode": "simulated", "detail": "N8N_WEBHOOK_URL is not configured."}

    payload = {
        "run_id": run["id"],
        "action": {k: action.get(k) for k in ("type", "recipient", "subject")},
        "report_markdown": run.get("report_markdown") or "",
        "approved_by": approver,
        "approved_at": now_iso(),
    }
    headers = {"Idempotency-Key": f"{run['id']}:{action.get('type')}"}
    if settings.n8n_webhook_secret:
        headers["X-Webhook-Secret"] = settings.n8n_webhook_secret

    last_error = "unknown error"
    async with httpx.AsyncClient(timeout=15) as client:
        for attempt in range(3):
            try:
                response = await client.post(settings.n8n_webhook_url, json=payload, headers=headers)
                if response.status_code < 300:
                    return {"delivered": True, "mode": "n8n", "detail": f"HTTP {response.status_code}"}
                last_error = f"HTTP {response.status_code}"
                if response.status_code < 500:  # client errors will not succeed on retry
                    break
            except httpx.HTTPError as exc:
                last_error = type(exc).__name__
            await asyncio.sleep(2**attempt)
    return {"delivered": False, "mode": "n8n", "detail": last_error}
