"""Conditional routing for the workflow graph."""
from __future__ import annotations

from backend.config import get_settings
from backend.graph.state import WorkflowState


def route_after_review(state: WorkflowState) -> str:
    """'report' when verified; 'retry' while retries remain; otherwise 'fail'."""
    review = state.get("review_result") or {}
    if review.get("passed"):
        return "report"
    if review.get("fatal"):
        return "fail"
    if state.get("retry_count", 0) <= get_settings().max_review_retries:
        return "retry"
    return "fail"
