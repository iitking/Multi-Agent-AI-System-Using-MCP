"""Pydantic schemas for the REST API."""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class CreateRunRequest(BaseModel):
    request: str = Field(..., min_length=10, max_length=2000, description="The business analysis question")
    async_execution: bool = Field(default=False, description="Run in background or await completion")


class CreateRunResponse(BaseModel):
    run_id: str
    status: str
    message: str


class RunDetailResponse(BaseModel):
    id: str
    user: str
    request: str
    status: str
    created_at: str
    updated_at: str
    plan: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    report_markdown: str | None = None
    report_path: str | None = None
    external_action: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    events: list[dict[str, Any]] | None = None
    error: str | None = None


class ApproveActionRequest(BaseModel):
    decision: str = Field(default="approve", description="'approve' or 'reject'")
    notes: str | None = Field(default=None, description="Optional notes or instructions")


class ApproveActionResponse(BaseModel):
    run_id: str
    status: str
    delivery: dict[str, Any]


class ToolItem(BaseModel):
    name: str
    description: str


class ToolsCatalogResponse(BaseModel):
    servers: dict[str, list[ToolItem]]


class AuditEntryResponse(BaseModel):
    id: int
    ts: str
    run_id: str | None
    actor: str
    agent: str | None
    action: str
    tool: str | None
    status: str
    detail: str | None
    duration_ms: int | None


class MetricsResponse(BaseModel):
    total_runs: int
    completed_runs: int
    failed_runs: int
    completion_rate_pct: float
    total_tool_calls: int
    tool_success_rate_pct: float
    avg_duration_ms: float
    total_estimated_cost_usd: float


class HealthResponse(BaseModel):
    status: str
    app_env: str
    analytics_db_ready: bool
    app_db_ready: bool
    docs_count: int
