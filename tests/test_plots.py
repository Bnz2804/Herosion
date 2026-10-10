import asyncio
import csv
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from africa_extension_agent import audit, importers, pii, plot_matching, tools as t, weather_sync
from africa_extension_agent.agent import run_agent
from africa_extension_agent.db.connection import connect, connect_readonly
from africa_extension_agent.service import create_app

from .stub_model import make_plot_stub

SRC = Path(__file__).resolve().parents[1] / "src" / "africa_extension_agent"


def test_plot_level_weather_differs_by_cell(db):
    c = connect_readonly(db)
    a = t.get_rainfall_evidence(c, plot_id="PL-GLZ001-001")
    b = t.get_rainfall_evidence(c, plot_id="PL-GLZ001-009")
    assert a["observed"]["current_dry_spell_days"] == 8 and b["observed"]["current_dry_spell_days"] == 1
    assert a["location"]["cell_id"] != b["location"]["cell_id"] and "not an on-farm gauge" in a["location"]["resolution_note"]
    assert t.get_rainfall_evidence(c, plot_id="PL-NOPE")["found"] is False
    assert t.get_rainfall_evidence(c)["found"] is False                      # neither plot nor cluster -> no guess
    assert t.get_rainfall_evidence(c, plot_id="PL-GLZ002-001")["evidence_sufficiency"] == "insufficient"


def test_household_tool_reports_location_quality_without_owner_data(db):
    c = connect_readonly(db)
    hh = {h["household_id"]: h for h in t.get_household_cluster(c, "GLZ-001")["households"]}
    assert "plot_geometry" in hh["HH-GLZ001-007"]["missing_fields"]
    assert hh["HH-GLZ001-007"]["plot"]["location_confidence"] == "very_low"
    assert hh["HH-GLZ001-012"]["plot"]["area_check"].startswith("mismatch")
    assert hh["HH-GLZ001-001"]["plot"]["location_confidence"] == "high"
    blob = json.dumps(hh).lower()
    assert not any(k in blob for k in ("full_name", "phone", "owner_name"))


def test_agent_side_code_never_touches_identity_store():
    for f in [*(SRC / "tools").glob("*.py"), SRC / "mcp_server.py", SRC / "agent.py"]:
        assert not re.search(r"\bpii\b|identity\.sqlite|farmer_identity", f.read_text()), f.name


def test_matching_flow_and_guards(db):
    conn = connect(db)
    res = plot_matching.candidates_for(conn, "PL-GLZ001-007")
    assert res["candidates"][0]["candidateId"] == "FC-GLZ-0001"            # nearest + area ~ declared 1.1 ha
    with pytest.raises(plot_matching.MatchError) as e:
        plot_matching.confirm_match(conn, "PL-GLZ001-007", "FC-GLZ-0001", "x")
    assert e.value.status == 400
    out = plot_matching.confirm_match(conn, "PL-GLZ001-007", "FC-GLZ-0001", "Aminata Soglo")
    assert out["verificationLevel"] == "officer_matched"
    h = {h["household_id"]: h for h in t.get_household_cluster(connect_readonly(db), "GLZ-001")["households"]}["HH-GLZ001-007"]
    assert h["plot"]["location_precision"] == "polygon" and "plot_geometry" not in h["missing_fields"]
    with pytest.raises(plot_matching.MatchError) as e:                       # same field to another plot
        plot_matching.confirm_match(conn, "PL-GLZ001-003", "FC-GLZ-0001", "Aminata Soglo")
    assert e.value.status == 409
    with pytest.raises(plot_matching.MatchError) as e:                       # surveyed plots are protected
        plot_matching.confirm_match(conn, "PL-GLZ001-001", "FC-GLZ-0002", "Aminata Soglo")
    assert e.value.status == 409
    assert conn.execute("SELECT officer FROM plot_match_log").fetchone()[0] == "Aminata Soglo"


def _square(lon, lat, d=0.0004):
    return {"type": "Feature", "properties": {"id": f"{lon}{lat}"},
            "geometry": {"type": "Polygon", "coordinates": [[[lon, lat], [lon + d, lat], [lon + d, lat + d], [lon, lat + d], [lon, lat]]]}}


def test_field_import_quality_report_and_geoparquet(db, tmp_path):
    conn = connect(db)
    feats = [_square(2.30, 7.90), _square(2.30, 7.90), _square(7.9, 2.3),            # dup, swapped lon/lat
             _square(2.31, 7.91, 0.00001), {"type": "Feature", "geometry": None}]  # tiny, no geometry
    f = tmp_path / "fields.geojson"
    f.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    rep = importers.import_fields(conn, str(f), "ftw-test", id_property="id")
    assert rep["imported"] == 1 and rep["duplicate"] == 1 and rep["read"] == 5
    assert sum(rep["skipped"].values()) == 3
    pytest.importorskip("pyarrow"); pytest.importorskip("shapely")
    import pyarrow as pa, pyarrow.parquet as pq, shapely.geometry as sg
    g = sg.Polygon([(2.40, 7.80), (2.4004, 7.80), (2.4004, 7.8004), (2.40, 7.8004)])
    pq.write_table(pa.table({"geometry": [g.wkb], "id": ["p1"]}), tmp_path / "f.parquet")
    rep = importers.import_fields(conn, str(tmp_path / "f.parquet"), "ftw-pq", id_property="id", bbox=(2.3, 7.7, 2.5, 7.9))
    assert rep["imported"] == 1


def test_plot_csv_import_consent_and_pseudonymity(db, tmp_path):
    conn = connect(db)
    f = tmp_path / "farmers.csv"
    with open(f, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "cluster_id", "area_ha", "lat", "lon", "owner_name", "phone", "consent"])
        w.writerow(["COOP-1", "GLZ-002", "1.2", "7.99", "2.40", "Test Person", "+22900000000", "yes"])
        w.writerow(["COOP-2", "GLZ-002", "0.8", "7.99", "2.41", "No Consent", "+22900000001", "no"])
        w.writerow(["COOP-3", "GLZ-002", "0.8", "2.41", "7.99", "Swapped", "", "yes"])
        w.writerow(["COOP-1", "GLZ-002", "1.2", "7.99", "2.40", "Dup", "", "yes"])
        w.writerow(["COOP-4", "NOPE-1", "1", "7.99", "2.40", "", "", ""])
    rep = importers.import_plots_csv(conn, str(f), "cooperative_file", pii_path=str(tmp_path / "id.sqlite"))
    assert rep["imported"] == 2 and rep["identity_stored_with_consent"] == 1
    assert sum(rep["rejected"].values()) == 3
    dump = json.dumps(t.get_household_cluster(connect_readonly(db), "GLZ-002"))
    assert "Test Person" not in dump and "No Consent" not in dump
    code = conn.execute("SELECT farmer_code FROM households WHERE household_id LIKE 'HH-GLZ002-005'").fetchone()[0]
    assert pii.reveal(code, "Officer A", "visit scheduling", str(tmp_path / "id.sqlite"))["full_name"] == "Test Person"
    with pytest.raises(ValueError):
        pii.reveal(code, "A", "x", str(tmp_path / "id.sqlite"))
    other = conn.execute("SELECT farmer_code FROM households WHERE household_id LIKE 'HH-GLZ002-006'").fetchone()[0]
    assert pii.reveal(other, "Officer A", "visit scheduling", str(tmp_path / "id.sqlite")) is None   # no consent -> nothing


class FakeProvider:
    name = "fake"

    def fetch(self, lat, lon, today, past_days, forecast_days):
        return {"observed": [(f"2026-06-0{i}", 2.0 * i) for i in range(1, 4)], "forecast": [("2026-06-04", 5.0, 0.8)],
                "issued_on": "2026-06-03", "source_obs": "fake-analysis", "source_fc": "fake-forecast"}


class Broken:
    name = "broken"

    def fetch(self, *a):
        raise TimeoutError("offline")


def test_weather_sync_updates_and_survives_failures(db):
    from datetime import date
    conn = connect(db)
    before = conn.execute("SELECT COUNT(*) FROM weather_obs_grid").fetchone()[0]
    bad = weather_sync.sync(conn, Broken(), today=date(2026, 6, 3))
    assert all(r["status"] == "error" for r in bad) and conn.execute("SELECT COUNT(*) FROM weather_obs_grid").fetchone()[0] == before
    ok = weather_sync.sync(conn, FakeProvider(), today=date(2026, 6, 3))
    assert all(r["status"] == "ok" for r in ok)
    r = t.get_rainfall_evidence(connect_readonly(db), plot_id="PL-GLZ001-001", as_of="2026-06-03")
    assert r["sources"]["observed"] in ("fake-analysis", "synthetic-grid") and r["forecast"]["first_wet_day"] == "2026-06-04"


def test_validator_blocks_citing_another_cells_rain(db):
    events = []
    out, session, state = asyncio.run(run_agent("GLZ-001 maize: should HH-GLZ001-001 delay?", model=make_plot_stub(wrong_cell_first=True),
                                               db_path=str(db), emit=lambda k, x: events.append((k, x))))
    rain_calls = [r for r in audit.read_log(session) if r["tool_name"] == "get_rainfall_evidence"]
    assert len(rain_calls) == 2                       # first wrong-cell attempt, then the correct plot
    assert "'PL-GLZ001-001'" not in rain_calls[0]["arguments_json"] and "PL-GLZ001-001" in rain_calls[1]["arguments_json"]
    assert "8 d" in out.household_recommendations[0].rationale


def test_service_exposes_candidates_match_and_cell_specific_evidence(db):
    c = TestClient(create_app(model_override=make_plot_stub()))
    plots = c.get("/clusters/GLZ-001/plots").json()
    p7 = next(p for p in plots if p["plotId"] == "PL-GLZ001-007")
    assert p7["locationPrecision"] == "village_centroid" and p7["geometry"] is None
    cand = c.get("/plots/PL-GLZ001-007/candidates").json()["candidates"]
    assert cand and cand[0]["geometry"]["type"] == "Polygon"
    assert c.post("/plots/PL-GLZ001-007/match", json={"candidateId": cand[0]["candidateId"], "officerName": "A"}).status_code == 422
    r = c.post("/plots/PL-GLZ001-007/match", json={"candidateId": cand[0]["candidateId"], "officerName": "Aminata Soglo"})
    assert r.status_code == 200 and r.json()["verificationLevel"] == "officer_matched"
    assert c.post("/plots/PL-GLZ001-003/match", json={"candidateId": cand[0]["candidateId"], "officerName": "Aminata Soglo"}).status_code == 409
    run = c.post("/runs", json={"clusterId": "GLZ-001", "question": "Should HH-GLZ001-001 delay planting?"}).json()
    ids = run["householdRecommendations"][0]["evidenceIds"]
    assert any(i.startswith("rainfall:g050_7.975_2.225") for i in ids) and not any("2.275" in i for i in ids)
    assert "plot:PL-GLZ001-001" in ids and not any(i.startswith("plot:") and i != "plot:PL-GLZ001-001" for i in ids)


def test_validator_rejects_misread_numbers_and_accepts_the_corrected_answer(db):
    out, session, state = asyncio.run(run_agent("GLZ-001 maize: should HH-GLZ001-001 delay?", model=make_plot_stub(wrong_facts_first=True),
                                               db_path=str(db), emit=lambda k, x: None))
    assert out.cell_facts[0].current_dry_spell_days == 8                      # corrected after the validator's pushback
    assert out.cell_facts[0].cell_id == "g050_7.975_2.225"


def test_validator_checks_onset_against_the_crop_rule():
    from africa_extension_agent.agent import CellFacts, RunState
    st = RunState(rain={"call-1": {"cell": "c", "dry": 1, "last7": 30.4, "wet": "2026-04-18", "max3": 51.0}}, onset_mm=20.0)
    ok = CellFacts(cell_id="c", rainfall_call_id="call-1", current_dry_spell_days=1, rain_last_7d_mm=30.4,
                   forecast_first_wet_day="2026-04-18", onset_rule_met_in_window=True)
    assert ok.onset_rule_met_in_window == (st.rain["call-1"]["max3"] >= st.onset_mm)


def _run_target(db, target, **kw):
    events = []
    out, session, state = asyncio.run(run_agent(f"GLZ-001 maize: should {target} delay?", model=make_plot_stub(target=target, **kw),
                                               db_path=str(db), emit=lambda k, x: events.append((k, x))))
    return out.household_recommendations[0].recommendation, session


def test_delay_rejected_when_planned_date_is_after_the_rain_returns(db):
    # HH-GLZ001-003 plans to plant 2026-04-20; forecast rain returns 2026-04-18 -> "delay" must be rejected, then corrected
    rec, _ = _run_target(db, "HH-GLZ001-003", delay_wrongly_first=True)
    assert rec == "proceed_with_planting"


def test_recommendations_follow_the_code_computed_assessment(db):
    assert _run_target(db, "HH-GLZ001-001")[0] == "delay_planting"          # west cell: 10 dry days after sowing > 7
    assert _run_target(db, "HH-GLZ001-009")[0] == "proceed_with_planting"   # east cell: 3 dry days after sowing
    assert _run_target(db, "HH-GLZ001-012")[0] == "proceed_with_planting"   # plans to sow after the rain returns


def test_validator_forces_the_agent_to_call_the_assessment_first(db):
    from africa_extension_agent import audit
    rec, session = _run_target(db, "HH-GLZ001-001", skip_assess_first=True)
    assert rec == "delay_planting"
    assert [r["tool_name"] for r in audit.read_log(session)].count("assess_planting_window") == 1   # called after the pushback


def test_conclusion_is_generated_from_the_validated_table_and_cannot_contradict_it(db):
    from africa_extension_agent.agent import CellFacts, ExtensionAdvice, HouseholdRecommendation, RunState, build_conclusion
    rec = lambda h, k: HouseholdRecommendation(household_id=h, recommendation=k, rationale="x", evidence_ids=["c"])  # noqa: E731
    adv = ExtensionAdvice(conclusion="Delay everyone!", evidence_ids=["c"], household_recommendations=[
        rec("HH-A", "delay_planting"), rec("HH-B", "may_not_exist" if False else "proceed_with_planting"), rec("HH-C", "insufficient_evidence")],
        cell_facts=[CellFacts(cell_id="g1", rainfall_call_id="c", current_dry_spell_days=1, rain_last_7d_mm=30.4,
                              forecast_first_wet_day="2026-04-18", onset_rule_met_in_window=True)])
    text = build_conclusion(adv, RunState(as_of="2026-04-10"))
    assert "Delay everyone" not in text and "Dataset date 2026-04-10" in text
    assert "Consider delaying planting (1): HH-A." in text and "May proceed (1): HH-B." in text and "Insufficient evidence (1): HH-C." in text
    assert "1 d dry spell" in text and "30.4 mm" in text and "onset rule met" in text


def test_run_returns_generated_conclusion_and_keeps_the_agent_note(db):
    out, session, state = asyncio.run(run_agent("GLZ-001 maize: should HH-GLZ001-001 delay?", model=make_plot_stub(),
                                               db_path=str(db), emit=lambda k, x: None))
    assert out.conclusion.startswith("Dataset date 2026-04-10.") and "HH-GLZ001-001" in out.conclusion
    assert state.agent_note == "Plot-level check."
