"""LangGraph workflow: planner -> (data analyst || researcher) -> insight -> reviewer -> report.

The reviewer can send work back to the insight agent a bounded number of times.
LangSmith traces the graph automatically when LANGSMITH_TRACING=true and LANGSMITH_API_KEY is set.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from backend.agents import data_analyst, insight, planner, report_agent, researcher, reviewer
from backend.agents.common import event
from backend.graph.routing import route_after_review
from backend.graph.state import WorkflowState
from backend.services.run_store import new_run_id

_GRAPH = None


async def fail_node(state: WorkflowState) -> dict[str, Any]:
    issues = (state.get("review_result") or {}).get("issues", [])
    message = "Review did not pass: " + ("; ".join(issues)[:400] or "no verifiable analysis")
    return {"status": "failed", "errors": [message], "events": [event("supervisor", message, "error")]}


def build_graph():
    graph = StateGraph(WorkflowState)
    graph.add_node("planner", planner.run)
    graph.add_node("data_analyst", data_analyst.run)
    graph.add_node("researcher", researcher.run)
    graph.add_node("insight", insight.run)
    graph.add_node("reviewer", reviewer.run)
    graph.add_node("report", report_agent.run)
    graph.add_node("fail", fail_node)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "data_analyst")  # independent tasks run in parallel
    graph.add_edge("planner", "researcher")
    graph.add_edge(["data_analyst", "researcher"], "insight")  # join: wait for both
    graph.add_edge("insight", "reviewer")
    graph.add_conditional_edges("reviewer", route_after_review, {"report": "report", "retry": "insight", "fail": "fail"})
    graph.add_edge("report", END)
    graph.add_edge("fail", END)
    return graph.compile(checkpointer=MemorySaver())  # use a Postgres checkpointer in production


def get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


ProgressCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


async def run_workflow(
    request: str,
    run_id: str | None = None,
    user: str = "system",
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Execute the graph and return the final state."""
    run_id = run_id or new_run_id()
    config = {"configurable": {"thread_id": run_id}, "run_name": "multi_agent_analysis",
              "metadata": {"run_id": run_id, "user": user}}
    initial: WorkflowState = {
        "run_id": run_id, "user": user, "request": request, "retry_count": 0, "review_feedback": [],
        "tool_calls": [], "events": [], "errors": [], "llm_usage": [], "status": "running",
    }
    graph = get_graph()
    async for chunk in graph.astream(initial, config, stream_mode="updates"):
        if on_progress:
            for node, update in chunk.items():
                await on_progress(node, update or {})
    snapshot = await graph.aget_state(config)
    return dict(snapshot.values)
