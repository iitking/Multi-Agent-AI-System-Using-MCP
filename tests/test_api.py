"""Integration tests for FastAPI endpoints: auth, runs, approval, tools, audit, and metrics."""
import pytest
from fastapi.testclient import TestClient

from backend.database.seed import ensure_seeded
from backend.main import app

client = TestClient(app)
ADMIN_HEADERS = {"X-API-Key": "dev-admin-key"}
ANALYST_HEADERS = {"X-API-Key": "dev-analyst-key"}
VIEWER_HEADERS = {"X-API-Key": "dev-viewer-key"}


@pytest.fixture(scope="module", autouse=True)
def setup_environment():
    ensure_seeded()


def test_public_health_and_root():
    root = client.get("/")
    assert root.status_code == 200
    assert root.json()["service"] == "Enterprise Multi-Agent AI System"

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    api_health = client.get("/api/health")
    assert api_health.status_code == 200
    assert api_health.json()["status"] == "ok"


def test_auth_unauthorized():
    res = client.get("/api/runs")
    assert res.status_code == 401


def test_auth_invalid_key():
    res = client.get("/api/runs", headers={"X-API-Key": "invalid-key"})
    assert res.status_code == 401


def test_rbac_permissions():
    # Viewer cannot create runs
    res = client.post("/api/runs", json={"request": "Valid question for sales report?"}, headers=VIEWER_HEADERS)
    assert res.status_code == 403

    # Viewer cannot read audit logs
    res_audit = client.get("/api/audit", headers=VIEWER_HEADERS)
    assert res_audit.status_code == 403

    # Analyst can read metrics
    res_metrics = client.get("/api/metrics", headers=ANALYST_HEADERS)
    assert res_metrics.status_code == 200

    # Admin can read audit
    res_admin_audit = client.get("/api/audit", headers=ADMIN_HEADERS)
    assert res_admin_audit.status_code == 200


def test_tools_discovery():
    res = client.get("/api/tools", headers=ADMIN_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert "data" in data["servers"]
    assert "research" in data["servers"]
    assert "document" in data["servers"]


def test_run_creation_and_lifecycle():
    # Submit run with an email requiring human approval
    question = "Analyze sales revenue drop in 2025 and email report to exec@company.com"
    res = client.post("/api/runs", json={"request": question}, headers=ADMIN_HEADERS)
    assert res.status_code == 201
    run_id = res.json()["run_id"]
    assert run_id.startswith("run_")

    # Fetch run
    get_run = client.get(f"/api/runs/{run_id}", headers=ADMIN_HEADERS)
    assert get_run.status_code == 200
    data = get_run.json()
    assert data["status"] == "report_ready"
    assert data["external_action"] is not None
    assert data["external_action"]["type"] == "email"

    # Fetch report
    report = client.get(f"/api/runs/{run_id}/report", headers=ADMIN_HEADERS)
    assert report.status_code == 200
    assert "Report" in report.text

    # Analyst cannot approve
    analyst_approve = client.post(
        f"/api/runs/{run_id}/approve",
        json={"decision": "approve"},
        headers=ANALYST_HEADERS,
    )
    assert analyst_approve.status_code == 403

    # Admin approves action
    admin_approve = client.post(
        f"/api/runs/{run_id}/approve",
        json={"decision": "approve", "notes": "Approved for distribution"},
        headers=ADMIN_HEADERS,
    )
    assert admin_approve.status_code == 200
    assert admin_approve.json()["status"] == "completed"

    # Check updated run
    final_run = client.get(f"/api/runs/{run_id}", headers=ADMIN_HEADERS).json()
    assert final_run["status"] == "completed"
