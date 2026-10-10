"""assess_planting_window: DETERMINISTIC planting-risk check per plot.

Combines three things no other tool joins: the household's plan (planted? planned date? irrigation), the crop's
rule (max safe dry spell after sowing, planting window), and the forecast of the plot's OWN weather cell.
The key quantity is the number of dry days AFTER the sowing date until rain is forecast to return, compared with
the crop's maximum safe dry spell. The model must not re-derive this; it explains the result.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from .. import geo
from ._util import as_of_date
from .crop import get_crop_context
from .plots import describe, plot_for
from .rainfall import _load

SUGGESTION = {
    "exceeds_safe_limit": "delay_planting", "before_planting_window": "delay_planting",
    "within_safe_limit": "proceed_with_planting", "after_rain_return": "proceed_with_planting",
    "irrigated_mitigated": "proceed_with_planting", "already_planted": "already_planted_monitor",
    "cannot_assess": "insufficient_evidence", "unknown_beyond_forecast": "insufficient_evidence",
    "planting_window_closed": "insufficient_evidence",
}


def _assess_one(conn: sqlite3.Connection, pid: str, today: date, as_of: str | None) -> dict:
    prow = plot_for(conn, pid)
    if prow is None:
        return {"plot_id": pid, "found": False, "risk": "cannot_assess", "rule_based_suggestion": "insufficient_evidence",
                "notes": ["unknown plot id; do not guess"]}
    h = conn.execute("SELECT * FROM households WHERE household_id=?", (prow["household_id"],)).fetchone()
    d = describe(prow)
    cell = geo.grid_cell(prow["centroid_lat"], prow["centroid_lon"])["cell_id"]
    out = {"found": True, "household_id": h["household_id"], "plot_id": pid, "crop": h["crop"],
           "planting_status": h["planting_status"], "planned_planting_date": h["planned_planting_date"],
           "irrigated": bool(h["has_irrigation"]), "weather_cell_id": cell,
           "location_confidence": d["location_confidence"], "verification_level": d["verification_level"], "notes": []}

    def done(risk, **kw):
        out.update(risk=risk, rule_based_suggestion=SUGGESTION[risk], **kw)
        return out

    cc = get_crop_context(conn, h["crop"], h["cluster_id"], as_of)
    if cc["calendar_status"] == "no_calendar_data":
        return done("cannot_assess", reason=f"no crop calendar for {h['crop']} in this zone")
    rule = cc["relevant_season"]
    max_safe, estab = rule["max_safe_dry_spell_days"], rule["establishment_days"]
    out.update(max_safe_dry_spell_days=max_safe, establishment_days=estab, calendar_status=cc["calendar_status"],
               planting_window=[rule["window_start"], rule["window_end"]])

    start = today - timedelta(days=20)
    obs, _last, fc, _os, _fs = _load(conn, "cell", cell, start, today, 14)
    last7 = [obs[x] for x in ((today - timedelta(days=i)).isoformat() for i in range(7)) if x in obs]
    out["recent_rain_7d_mm"] = round(sum(last7), 1) if last7 else None
    wet = next((r["forecast_date"] for r in fc if r["rain_probability"] >= 0.5 and r["expected_mm"] >= 5), None)
    out["forecast_first_wet_day"] = wet
    out["forecast_days_covered"] = len(fc)

    if h["planting_status"] == "planted":
        if not h["planting_date"]:
            return done("cannot_assess", reason="planted but planting date not recorded")
        since = (today - date.fromisoformat(h["planting_date"])).days
        dry_run = 0
        for i in range(max(since, 0) + 1):
            v = obs.get((today - timedelta(days=i)).isoformat())
            if v is None or v >= 1.0:
                break
            dry_run += 1
        ahead = 0
        for r in fc:
            if r["rain_probability"] >= 0.5:
                break
            ahead += 1
        total = dry_run + ahead
        out.update(days_since_planting=since, projected_dry_days_after_sowing=total,
                   in_establishment_window=since < estab)
        if since < estab and total > max_safe:
            out["notes"].append(f"establishment risk: about {total} dry days after sowing vs safe limit {max_safe}")
        return done("already_planted")

    if cc["calendar_status"] == "before_window":
        return done("before_planting_window", reason=f"planting window opens {rule['window_start']}")
    if cc["calendar_status"] == "after_window":
        return done("planting_window_closed", reason=f"planting window closed {rule['window_end']}")
    if not h["planned_planting_date"]:
        return done("cannot_assess", reason="planned planting date not recorded")
    if not fc:
        return done("cannot_assess", reason="no forecast for this weather cell")

    planned = date.fromisoformat(h["planned_planting_date"])
    sowing = max(planned, today)
    if planned < today:
        out["notes"].append("planned date is in the past; assessed from today")
    out["assumed_sowing_date"] = sowing.isoformat()
    if wet is not None:
        dry_after = max((date.fromisoformat(wet) - sowing).days, 0)
        out["projected_dry_days_after_sowing"] = dry_after
        risk = "after_rain_return" if sowing >= date.fromisoformat(wet) else (
            "exceeds_safe_limit" if dry_after > max_safe else "within_safe_limit")
    else:
        lower = (date.fromisoformat(fc[-1]["forecast_date"]) - sowing).days + 1
        out["projected_dry_days_after_sowing"] = lower
        out["notes"].append(f"no rain forecast through {fc[-1]['forecast_date']}; value is a lower bound")
        risk = "exceeds_safe_limit" if lower > max_safe else "unknown_beyond_forecast"
    if risk == "exceeds_safe_limit" and h["has_irrigation"]:
        risk = "irrigated_mitigated"
    if d["location_confidence"] in ("low", "very_low"):
        out["notes"].append(f"weather is for an approximate location ({d['location_confidence']} confidence)")
    return done(risk)


def assess_planting_window(conn: sqlite3.Connection, plot_ids: list[str], as_of: str | None = None) -> dict:
    today = as_of_date(conn, as_of)
    items = [_assess_one(conn, pid, today, as_of) for pid in dict.fromkeys(plot_ids[:50])]
    by = {}
    for a in items:
        by[a["risk"]] = by.get(a["risk"], 0) + 1
    return {"found": True, "as_of": today.isoformat(), "assessments": items,
            "summary": f"{len(items)} plot(s) assessed as of {today}: " + ", ".join(f"{n} {k}" for k, n in sorted(by.items())) + "."}
