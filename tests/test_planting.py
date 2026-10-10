import json

from africa_extension_agent import tools as t
from africa_extension_agent.db.connection import connect_readonly


def _assess(db, *pids):
    r = t.assess_planting_window(connect_readonly(db), list(pids))
    return {a.get("household_id", a["plot_id"]): a for a in r["assessments"]}


def test_glz001_scenarios_produce_both_positive_and_negative_recommendations(db):
    a = _assess(db, *[f"PL-GLZ001-{n:03d}" for n in (1, 2, 3, 4, 5, 7, 9, 11, 12)])
    sug = {h: v["rule_based_suggestion"] for h, v in a.items()}
    assert sug["HH-GLZ001-001"] == "delay_planting" and a["HH-GLZ001-001"]["projected_dry_days_after_sowing"] == 10
    assert sug["HH-GLZ001-002"] == "delay_planting" and a["HH-GLZ001-002"]["projected_dry_days_after_sowing"] == 8
    assert a["HH-GLZ001-003"]["risk"] == "after_rain_return"                  # plans 24 Apr, rain returns 22 Apr
    assert a["HH-GLZ001-004"]["risk"] == "irrigated_mitigated"                # would exceed, but irrigated
    assert sug["HH-GLZ001-005"] == "already_planted_monitor"
    assert sug["HH-GLZ001-007"] == "insufficient_evidence" and "planned planting date" in a["HH-GLZ001-007"]["reason"]
    assert a["HH-GLZ001-009"]["risk"] == "within_safe_limit" and a["HH-GLZ001-009"]["projected_dry_days_after_sowing"] == 3
    assert a["HH-GLZ001-011"]["risk"] == "after_rain_return" and a["HH-GLZ001-012"]["risk"] == "after_rain_return"
    # plot-level weather decides: east and west cells differ
    assert a["HH-GLZ001-001"]["forecast_first_wet_day"] == "2026-04-22" and a["HH-GLZ001-009"]["forecast_first_wet_day"] == "2026-04-16"
    assert a["HH-GLZ001-012"]["notes"] and "approximate location" in " ".join(a["HH-GLZ001-012"]["notes"])


def test_other_clusters_and_missing_data_are_handled_honestly(db):
    a = _assess(db, "PL-KAN001-001", "PL-GLZ002-001", "PL-NOPE")
    assert a["HH-KAN001-001"]["risk"] == "before_planting_window"             # sowing 15 Apr, window opens 20 May
    assert a["HH-GLZ002-001"]["risk"] == "cannot_assess"                      # rain-station outage: no forecast
    r = t.assess_planting_window(connect_readonly(db), ["PL-NOPE"])["assessments"][0]
    assert r["found"] is False and r["rule_based_suggestion"] == "insufficient_evidence"


def test_assessment_exposes_no_owner_data(db):
    blob = json.dumps(t.assess_planting_window(connect_readonly(db), ["PL-GLZ001-001"])).lower()
    assert not any(k in blob for k in ("full_name", "phone", "owner_name", "farmer_code"))
