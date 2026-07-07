"""End-to-end tests for the LangGraph multi-agent workflow."""
import pytest

from backend.database.seed import ensure_seeded
from backend.graph.workflow import run_workflow


@pytest.fixture(scope="module", autouse=True)
def setup_environment():
    ensure_seeded()


@pytest.mark.asyncio
async def test_full_workflow_execution():
    request = "Analyze sales data, explain why revenue dropped, and find our top-performing products."
    events = []

    async def on_progress(node: str, update: dict):
        events.append(node)

    state = await run_workflow(request, user="tester", on_progress=on_progress)

    # Validate graph traversed all nodes
    assert "planner" in events
    assert "data_analyst" in events
    assert "researcher" in events
    assert "insight" in events
    assert "reviewer" in events
    assert "report" in events

    # Check state results
    assert state["status"] == "report_ready"
    assert state["review_result"]["passed"] is True
    assert state["report"]["path"].endswith(".md")
    assert len(state["tool_calls"]) > 10
    assert len(state["insight_result"]["findings"]) >= 3
