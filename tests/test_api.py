import pytest
from fastapi.testclient import TestClient

from complianceops.api import create_app, get_service
from complianceops.config import Settings
from complianceops.service import ComplianceService


@pytest.fixture
def client(tmp_path):
    service = ComplianceService(Settings(memory_db_path=str(tmp_path / "api.db")))
    app = create_app()
    app.dependency_overrides[get_service] = lambda: service
    with TestClient(app) as client:
        yield client


def payload(**kwargs):
    return {
        "audit_id": "AUD-api",
        "request": "Assess current evidence.",
        "control_ids": ["AC-01"],
        **kwargs,
    }


def test_root_redirects_to_interactive_docs(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/docs"
    assert client.get("/docs").status_code == 200


def test_api_full_lifecycle(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert len(client.get("/v1/controls").json()["controls"]) == 3
    response = client.post("/v1/assessments", json=payload(architecture="multi_agent"))
    assert response.status_code == 200
    run = response.json()
    path = f"/v1/audits/AUD-api/runs/{run['run_id']}"
    assert client.get(path).json() == run
    assert client.get(f"/v1/audits/AUD-other/runs/{run['run_id']}").status_code == 404
    assert client.get("/v1/audits/AUD-api/memory").json()["run_count"] == 1
    assert client.delete("/v1/audits/AUD-api/memory").status_code == 204
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("change", [
    {"audit_id": "INC-invalid"},
    {"request": "   "},
    {"architecture": "unknown"},
    {"control_ids": []},
    {"control_ids": ["NONEXISTENT"]},
    {"control_ids": ["AC-01", "AC-01"]},
    {"execute": True},
])
def test_invalid_contracts(client, change):
    assert client.post("/v1/assessments", json=payload(**change)).status_code == 422


def test_memory_path_is_validated(client):
    assert client.get("/v1/audits/invalid/memory").status_code == 422


def test_live_error_is_explicit(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app = create_app()
    app.dependency_overrides[get_service] = lambda: ComplianceService(Settings(
        runtime_mode="live", memory_db_path=str(tmp_path / "live.db"),
    ))
    with TestClient(app) as client:
        response = client.post("/v1/assessments", json=payload())
    assert response.status_code == 502
    assert "no completed assessment" in response.json()["detail"]
