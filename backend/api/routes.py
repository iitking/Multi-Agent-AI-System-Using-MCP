"""REST API endpoints for multi-agent execution, human approvals, tools discovery, and auditing."""
from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status

from backend.api.auth import AuthUser, require_permission
from backend.api.schemas import (
    ApproveActionRequest,
    ApproveActionResponse,
    AuditEntryResponse,
    CreateRunRequest,
    CreateRunResponse,
    HealthResponse,
    MetricsResponse,
    RunDetailResponse,
    ToolItem,
    ToolsCatalogResponse,
)
from backend.config import get_settings
from backend.database.db import database_file_exists, get_analytics_readonly_engine, get_app_engine
from backend.graph.workflow import run_workflow
from backend.mcp_client import discover_tools
from backend.security.guard import validate_user_request
from backend.services import audit, n8n, research, run_store

router = APIRouter(prefix="/api", tags=["API"])


async def _execute_and_persist(run_id: str, request_text: str, username: str) -> dict[str, Any]:
    """Execute LangGraph workflow and persist updates to the database."""
    run_store.update_run(run_id, status="running")
    started = time.perf_counter()

    async def on_progress(node: str, update: dict[str, Any]) -> None:
        events = update.get("events")
        if events:
            current = run_store.get_run(run_id)
            existing_events = (current.get("events") if current else None) or []
            run_store.update_run(run_id, events=existing_events + events)

    try:
        final_state = await run_workflow(
            request=request_text,
            run_id=run_id,
            user=username,
            on_progress=on_progress,
        )

        duration_ms = int((time.perf_counter() - started) * 1000)
        tool_calls = final_state.get("tool_calls", [])
        llm_usage = final_state.get("llm_usage", [])
        total_cost = sum(float(u.get("cost_usd", 0)) for u in llm_usage)

        metrics = {
            "duration_ms": duration_ms,
            "tool_calls_count": len(tool_calls),
            "tool_calls_ok": sum(1 for c in tool_calls if c.get("ok")),
            "retry_count": final_state.get("retry_count", 0),
            "cost_usd": round(total_cost, 6),
            "llm_calls_count": len(llm_usage),
        }

        report = final_state.get("report") or {}
        report_markdown = report.get("markdown")
        report_path = report.get("path")
        errors = final_state.get("errors") or []
        final_status = final_state.get("status", "completed")

        run_store.update_run(
            run_id,
            status=final_status,
            plan=final_state.get("plan"),
            result={
                "data_result": final_state.get("data_result"),
                "research_result": final_state.get("research_result"),
                "insight_result": final_state.get("insight_result"),
                "review_result": final_state.get("review_result"),
            },
            report_markdown=report_markdown,
            report_path=report_path,
            external_action=final_state.get("external_action"),
            metrics=metrics,
            events=final_state.get("events", []),
            error="; ".join(errors) if errors else None,
        )

        audit.record(
            run_id=run_id,
            actor=username,
            action="workflow_completed",
            status="ok" if final_status in ("report_ready", "completed") else "failed",
            detail={"status": final_status, "metrics": metrics},
            duration_ms=duration_ms,
        )
        return final_state
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        err_msg = f"{type(exc).__name__}: {exc}"
        run_store.update_run(
            run_id,
            status="failed",
            error=err_msg,
            metrics={"duration_ms": duration_ms},
        )
        audit.record(
            run_id=run_id,
            actor=username,
            action="workflow_failed",
            status="error",
            detail={"error": err_msg},
            duration_ms=duration_ms,
        )
        raise


@router.post("/runs", response_model=CreateRunResponse, status_code=status.HTTP_201_CREATED)
async def create_run(
    payload: CreateRunRequest,
    background_tasks: BackgroundTasks,
    user: AuthUser = Depends(require_permission("runs:create")),
) -> CreateRunResponse:
    """Submit a business question to start a new multi-agent workflow run."""
    try:
        clean_request = validate_user_request(payload.request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    run_id = run_store.create_run(user=user.username, request=clean_request)
    audit.record(
        run_id=run_id,
        actor=user.username,
        action="run_created",
        status="ok",
        detail={"request": clean_request[:200]},
    )

    if payload.async_execution:
        background_tasks.add_task(_execute_and_persist, run_id, clean_request, user.username)
        return CreateRunResponse(
            run_id=run_id,
            status="queued",
            message="Workflow submitted for background execution.",
        )

    # Synchronous execution
    try:
        final_state = await _execute_and_persist(run_id, clean_request, user.username)
        return CreateRunResponse(
            run_id=run_id,
            status=final_state.get("status", "completed"),
            message="Workflow completed successfully.",
        )
    except Exception as exc:
        return CreateRunResponse(
            run_id=run_id,
            status="failed",
            message=f"Workflow failed: {exc}",
        )


@router.get("/runs", response_model=list[RunDetailResponse])
def list_runs(
    limit: int = Query(default=50, ge=1, le=200),
    user: AuthUser = Depends(require_permission("runs:read")),
) -> list[dict[str, Any]]:
    """List recent runs with metadata, status and metrics."""
    return run_store.list_runs(limit=limit)


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
def get_run(
    run_id: str,
    user: AuthUser = Depends(require_permission("runs:read")),
) -> dict[str, Any]:
    """Get the full details, plan, results, events, and metrics of a run."""
    run = run_store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run '{run_id}' not found.")
    return run


@router.get("/runs/{run_id}/report")
def get_run_report(
    run_id: str,
    user: AuthUser = Depends(require_permission("runs:read")),
) -> Response:
    """Retrieve the generated Markdown report for a completed run."""
    run = run_store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run '{run_id}' not found.")
    report_md = run.get("report_markdown")
    if not report_md:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' does not have a generated report yet (status: {run.get('status')}).",
        )
    return Response(content=report_md, media_type="text/markdown")


@router.post("/runs/{run_id}/approve", response_model=ApproveActionResponse)
async def approve_action(
    run_id: str,
    payload: ApproveActionRequest,
    user: AuthUser = Depends(require_permission("runs:approve")),
) -> ApproveActionResponse:
    """Human-in-the-loop approval: approve or reject an external business action (e.g. n8n delivery)."""
    run = run_store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run '{run_id}' not found.")

    action = run.get("external_action")
    if not action:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Run '{run_id}' has no pending external action to approve.",
        )

    if action.get("status") not in ("pending_approval", "pending"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"External action is already in state '{action.get('status')}'.",
        )

    decision = payload.decision.lower()
    if decision not in ("approve", "reject"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Decision must be either 'approve' or 'reject'.",
        )

    if decision == "reject":
        action["status"] = "rejected"
        action["rejection_notes"] = payload.notes
        run_store.update_run(run_id, external_action=action, status="action_rejected")
        audit.record(
            run_id=run_id,
            actor=user.username,
            action="action_rejected",
            status="ok",
            detail={"notes": payload.notes},
        )
        return ApproveActionResponse(
            run_id=run_id,
            status="action_rejected",
            delivery={"delivered": False, "mode": "rejected", "detail": "Action rejected by reviewer."},
        )

    # Decision == approve
    delivery = await n8n.dispatch_approved_action(run, approver=user.username)
    action["status"] = "dispatched" if delivery.get("delivered") else "simulated_delivered"
    action["delivery_result"] = delivery
    action["approved_by"] = user.username

    run_store.update_run(run_id, external_action=action, status="completed")
    audit.record(
        run_id=run_id,
        actor=user.username,
        action="action_approved",
        status="ok" if delivery.get("delivered") or delivery.get("mode") == "simulated" else "warning",
        detail={"delivery": delivery, "notes": payload.notes},
    )

    return ApproveActionResponse(
        run_id=run_id,
        status="completed",
        delivery=delivery,
    )


@router.get("/tools", response_model=ToolsCatalogResponse)
async def list_tools(
    user: AuthUser = Depends(require_permission("tools:read")),
) -> ToolsCatalogResponse:
    """Discover all approved tools exposed by Data, Research, and Document MCP servers."""
    catalog = await discover_tools()
    formatted = {
        server: [ToolItem(name=t["name"], description=t["description"]) for t in tools]
        for server, tools in catalog.items()
    }
    return ToolsCatalogResponse(servers=formatted)


@router.get("/audit", response_model=list[AuditEntryResponse])
def get_audit_trail(
    run_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    user: AuthUser = Depends(require_permission("audit:read")),
) -> list[dict[str, Any]]:
    """Retrieve full audit logs with filtering by run ID."""
    return audit.list_entries(run_id=run_id, limit=limit)


@router.get("/metrics", response_model=MetricsResponse)
def get_metrics(
    user: AuthUser = Depends(require_permission("metrics:read")),
) -> MetricsResponse:
    """Aggregate metrics across runs: completion rate, tool success rate, latency and cost."""
    all_runs = run_store.list_runs(limit=200)
    audit_entries = audit.list_entries(limit=1000)

    total_runs = len(all_runs)
    completed_runs = sum(1 for r in all_runs if r.get("status") in ("report_ready", "completed"))
    failed_runs = sum(1 for r in all_runs if r.get("status") in ("failed", "review_failed"))
    completion_rate = (completed_runs / total_runs * 100) if total_runs else 0.0

    tool_entries = [e for e in audit_entries if e.get("action") == "tool_call"]
    total_tool_calls = len(tool_entries)
    tool_success_rate = (
        (sum(1 for e in tool_entries if e.get("status") == "ok") / total_tool_calls * 100)
        if total_tool_calls
        else 100.0
    )

    durations = [r["metrics"]["duration_ms"] for r in all_runs if r.get("metrics") and "duration_ms" in r["metrics"]]
    avg_duration = sum(durations) / len(durations) if durations else 0.0

    costs = [r["metrics"]["cost_usd"] for r in all_runs if r.get("metrics") and "cost_usd" in r["metrics"]]
    total_cost = sum(costs)

    return MetricsResponse(
        total_runs=total_runs,
        completed_runs=completed_runs,
        failed_runs=failed_runs,
        completion_rate_pct=round(completion_rate, 2),
        total_tool_calls=total_tool_calls,
        tool_success_rate_pct=round(tool_success_rate, 2),
        avg_duration_ms=round(avg_duration, 2),
        total_estimated_cost_usd=round(total_cost, 6),
    )


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """System health check verifying database engines and docs directory."""
    settings = get_settings()
    analytics_ready = database_file_exists(settings.analytics_db_url)
    app_ready = database_file_exists(settings.app_db_url)
    docs = research.list_documents().get("documents", [])

    is_ok = analytics_ready and app_ready
    return HealthResponse(
        status="ok" if is_ok else "degraded",
        app_env=settings.app_env,
        analytics_db_ready=analytics_ready,
        app_db_ready=app_ready,
        docs_count=len(docs),
    )
