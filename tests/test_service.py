from fastapi.testclient import TestClient

from africa_extension_agent import audit
from africa_extension_agent.service import create_app

from .stub_model import make_stub

Q = "Which maize households in GLZ-001 should consider delaying planting?"


def client(model=None):
    return TestClient(create_app(model_override=model))


def test_read_views_match_workbench_contract(db):
    c = client(make_stub())
    cl = c.get("/clusters").json()
    assert {x["clusterId"] for x in cl} == {"GLZ-001", "GLZ-002", "ZGB-001", "KAN-001"}
    assert c.get("/clusters/NOPE/plots").status_code == 404
    plots = c.get("/clusters/GLZ-001/plots").json()
    assert plots[0].keys() >= {"plotId", "householdId", "householdName", "areaHa", "variety", "dataTier"}
    ev = c.get("/clusters/GLZ-002/evidence").json()["evidence"]
    rain = next(e for e in ev if e["kind"] == "rainfall")
    assert "insufficient" in rain["sourceStatus"] and "no data" in rain["detail"]
    assert not any(e["kind"] == "forecast" for e in ev)          # no forecast exists -> none invented
    assert c.get("/status").json()["farmerDeliveryEnabled"] is False


def test_run_returns_traceable_agent_payload(db):
    r = client(make_stub()).post("/runs", json={"clusterId": "GLZ-001", "question": Q})
    assert r.status_code == 201
    run = r.json()
    assert run["workflowMode"] == "agent_driven"
    assert [t["toolName"] for t in run["toolCalls"]] == [
        "get_household_cluster", "get_rainfall_evidence", "get_crop_context", "get_pest_reports"]
    assert all(t["auditCallId"] and t["decision"] for t in run["toolCalls"])
    logged = {x["call_id"] for x in audit.read_log(run["agentSessionId"])}
    assert {t["auditCallId"] for t in run["toolCalls"]} == logged
    ids = {e["evidenceId"] for e in run["evidence"]}
    delay = [x for x in run["householdRecommendations"] if x["recommendation"] == "delay_planting"]
    assert len(delay) == 4
    for rec in delay:                                            # every cited evidence id is a real item
        assert rec["evidenceIds"] and set(rec["evidenceIds"]) <= ids


def test_run_without_household_tool_cites_no_plot_evidence(db):
    run = client(make_stub()).post("/runs", json={"clusterId": "GLZ-002", "question": Q.replace("001", "002")}).json()
    assert [t["toolName"] for t in run["toolCalls"]] == ["get_household_cluster", "get_rainfall_evidence"]
    assert not any(e["kind"] == "crop_calendar" for e in run["evidence"])


def test_unconfigured_model_is_reported_not_faked(db, monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    c = TestClient(create_app(model_override="mistral:mistral-large-latest"))
    assert c.get("/status").json()["modelConfigured"] is False
    r = c.post("/runs", json={"clusterId": "GLZ-001", "question": Q})
    assert r.status_code == 503 and r.json()["detail"]["error"] == "model_not_configured"
    assert c.post("/runs", json={"clusterId": "NOPE", "question": Q}).status_code in (404, 503)


def test_service_token(db, monkeypatch):
    monkeypatch.setenv("AGENT_SERVICE_TOKEN", "s3cret")
    c = client(make_stub())
    assert c.get("/clusters").status_code == 401
    assert c.get("/clusters", headers={"X-Agent-Service-Token": "s3cret"}).status_code == 200


def test_crop_specific_evidence_only_for_matching_crop(db):
    run = client(make_stub()).post("/runs", json={"clusterId": "GLZ-001", "question": Q}).json()
    by_id = {e["evidenceId"]: e for e in run["evidence"]}
    for rec in run["householdRecommendations"]:
        for eid in rec["evidenceIds"]:
            assert by_id[eid].get("crop") in (None, rec["crop"])
    assert not any("cassava" in i or "cowpea" in i for r in run["householdRecommendations"] for i in r["evidenceIds"])


def test_status_reports_build_id(db):
    from africa_extension_agent import BUILD_ID
    assert client(make_stub()).get("/status").json()["agentBuild"] == BUILD_ID
