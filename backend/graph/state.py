"""Shared workflow state passed between agents (compact, structured - not chat history)."""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class WorkflowState(TypedDict, total=False):
    # inputs
    run_id: str
    user: str
    request: str
    # agent outputs (each is a structured result: status/findings/evidence/errors/next_action + extras)
    plan: dict[str, Any]
    data_result: dict[str, Any]
    research_result: dict[str, Any]
    insight_result: dict[str, Any]
    review_result: dict[str, Any]
    report: dict[str, Any]
    external_action: dict[str, Any] | None
    # control
    retry_count: int
    review_feedback: list[str]
    status: str
    # accumulated across (possibly parallel) nodes
    tool_calls: Annotated[list[dict[str, Any]], operator.add]
    events: Annotated[list[dict[str, Any]], operator.add]
    errors: Annotated[list[str], operator.add]
    llm_usage: Annotated[list[dict[str, Any]], operator.add]
