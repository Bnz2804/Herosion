import asyncio
import json
import os
import sys

from africa_extension_agent import audit
from africa_extension_agent import tools as t
from africa_extension_agent.agent import run_agent
from africa_extension_agent.db.connection import connect_readonly

from .stub_model import make_stub


def test_tools_are_distinct_and_honest(db):
    c = connect_readonly(db)
    rain = t.get_rainfall_evidence(c, "GLZ-001")
    assert rain["observed"]["current_dry_spell_days"] == 8
    assert rain["forecast"]["first_wet_day"] == "2026-04-18"
    assert rain["observed"]["missing_days"] == ["2026-03-24", "2026-03-25"]
    assert t.get_rainfall_evidence(c, "GLZ-002")["evidence_sufficiency"] == "insufficient"
    assert t.get_crop_context(c, "maize", "KAN-001")["calendar_status"] == "before_window"
    assert t.get_crop_context(c, "sorghum", "GLZ-001")["calendar_status"] == "no_calendar_data"
    assert t.get_pest_reports(c, "ZGB-001", "maize")["by_pest"][0]["confidence_note"].startswith("small sample")
    hh = t.get_household_cluster(c, "GLZ-001", "maize")["households"]
    assert any(h["missing_fields"] for h in hh)
    assert t.get_household_cluster(c, "NOPE")["found"] is False


def test_no_real_pii_shape(db):
    c = connect_readonly(db)
    codes = [r[0] for r in c.execute("SELECT farmer_code FROM households")]
    assert all(x.startswith("FRM-") for x in codes)


def test_mcp_roundtrip_and_audit(db, monkeypatch):
    from fastmcp.client import Client
    from fastmcp.client.transports import StdioTransport

    async def go():
        env = {**os.environ, "EXTENSION_AGENT_DB": str(db), "EXTENSION_AGENT_SESSION": "sess-t"}
        async with Client(StdioTransport(sys.executable, ["-m", "africa_extension_agent.mcp_server"], env=env)) as c:
            names = {x.name for x in await c.list_tools()}
            assert names == {"get_household_cluster", "get_rainfall_evidence", "get_crop_context", "get_pest_reports", "assess_planting_window"}
            r = await c.call_tool("get_crop_context", {"crop": "maize", "cluster_id": "GLZ-001"})
            return r.data["audit_call_id"]
    cid = asyncio.run(go())
    rows = audit.read_log("sess-t")
    assert [r["call_id"] for r in rows] == [cid] and rows[0]["status"] == "ok" and rows[0]["result_sha256"]


def _run(db, question, model):
    events = []
    out, session, state = asyncio.run(run_agent(question, model=model, db_path=str(db),
                                                emit=lambda k, x: events.append((k, x))))
    return out, session, state, events


def test_agent_branches_and_audits(db):
    out, session, state, ev = _run(db, "Which maize households in GLZ-001 should consider delaying planting?", make_stub())
    assert state.tool_calls == ["get_household_cluster", "get_rainfall_evidence", "get_crop_context", "get_pest_reports"]
    recs = {r.household_id: r.recommendation for r in out.household_recommendations}
    assert recs["HH-GLZ001-001"] == "delay_planting"
    assert recs["HH-GLZ001-003"] == "proceed_with_planting"
    assert recs["HH-GLZ001-004"] == "proceed_with_planting"      # irrigated
    assert recs["HH-GLZ001-005"] == "already_planted_monitor"
    assert recs["HH-GLZ001-007"] == "insufficient_evidence"      # missing planned date
    assert "HH-GLZ001-008" not in recs                           # cassava filtered out
    logged = [r["tool_name"] for r in audit.read_log(session)]
    assert logged == state.tool_calls                            # every call audited
    kinds = [k for k, _ in ev]
    assert kinds.index("tool_selected") < kinds.index("tool_result") < len(kinds)


def test_agent_stops_when_evidence_insufficient(db):
    out, session, state, _ = _run(db, "Which maize households in GLZ-002 should consider delaying planting?", make_stub())
    assert state.tool_calls == ["get_household_cluster", "get_rainfall_evidence"]  # different path
    assert {r.recommendation for r in out.household_recommendations} <= {"insufficient_evidence", "already_planted_monitor"}


def test_validator_rejects_fabricated_household(db):
    out, session, state, _ = _run(db, "Which maize households in GLZ-001 should consider delaying planting?",
                                  make_stub(bad_household_first=True))
    assert all(r.household_id != "HH-FAKE-999" for r in out.household_recommendations)
