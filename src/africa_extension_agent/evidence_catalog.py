"""Browsable, citable evidence records shaped for the Herosion officer workbench.

These are READ views over the same SQLite data the MCP tools use. The agent itself never calls this
module: it only uses MCP tools. The service uses it to (a) populate the workbench and (b) turn the
tool calls an agent actually made into citable evidence items.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import timedelta
from typing import Iterable

from . import tools
from .tools._util import as_of_date, cluster_row

TIER = "local_test_data"
KIND_BY_TOOL = {
    "get_household_cluster": {"plot"},
    "get_rainfall_evidence": {"rainfall", "forecast"},
    "get_crop_context": {"crop_calendar"},
    "get_pest_reports": {"pest_report"},
}


def plot_id(household_id: str) -> str:
    return "PL-" + household_id.removeprefix("HH-")


def _item(eid, kind, label, detail, observed_at, source, record_id, status):
    return {"evidenceId": eid, "kind": kind, "label": label, "detail": detail,
            "observedAt": observed_at, "sourceName": source, "sourceRecordId": record_id,
            "sourceStatus": status, "dataTier": TIER}


def list_clusters(conn: sqlite3.Connection) -> list[dict]:
    today = as_of_date(conn, None)
    out = []
    for c in conn.execute("SELECT * FROM clusters ORDER BY cluster_id"):
        cid = c["cluster_id"]
        n = conn.execute("SELECT COUNT(*) FROM households WHERE cluster_id=?", (cid,)).fetchone()[0]
        recent = (today - timedelta(days=14)).isoformat()
        open_pests = conn.execute(
            "SELECT COUNT(*) FROM pest_reports WHERE cluster_id=? AND report_date>=? AND fields_affected>0",
            (cid, recent)).fetchone()[0]
        out.append({"clusterId": cid, "name": c["name"], "commune": c["commune"], "department": c["department"],
                    "householdCount": n, "plotCount": n, "openPestReports": open_pests, "dataTier": TIER})
    return out


def list_plots(conn: sqlite3.Connection, cluster_id: str) -> list[dict]:
    rows = conn.execute("SELECT h.*, p.geometry_geojson, p.plot_id AS pid FROM households h LEFT JOIN plots p USING (household_id) "
                        "WHERE h.cluster_id=? ORDER BY h.household_id", (cluster_id,)).fetchall()
    loc = {h["household_id"]: h["plot"] for h in tools.get_household_cluster(conn, cluster_id)["households"]}
    out = []
    for r in rows:
        d = loc.get(r["household_id"]) or {}
        out.append({"plotId": plot_id(r["household_id"]), "householdId": r["household_id"],
                    "householdName": f"Household {r['farmer_code']}", "clusterId": cluster_id,
                    "areaHa": r["area_ha"] or 0.0, "crop": r["crop"], "variety": r["variety"] or "Not recorded",
                    "plantingStatus": r["planting_status"], "lastObservationDate": r["planting_date"], "dataTier": TIER,
                    "verificationLevel": d.get("verification_level"), "geometrySource": d.get("geometry_source"),
                    "locationConfidence": d.get("location_confidence"), "locationPrecision": d.get("location_precision"),
                    "centroidLat": (d.get("centroid") or {}).get("lat"), "centroidLon": (d.get("centroid") or {}).get("lon"),
                    "areaMappedHa": d.get("area_mapped_ha"), "areaCheck": d.get("area_check"),
                    "weatherCellId": d.get("weather_cell_id"), "tenureType": d.get("tenure_type"),
                    "geometry": json.loads(r["geometry_geojson"]) if r["geometry_geojson"] else None})
    return out


def plot_cells(conn: sqlite3.Connection, cluster_id: str) -> dict[str, str]:
    return {plot_id(h["household_id"]): h["plot"]["weather_cell_id"]
            for h in tools.get_household_cluster(conn, cluster_id)["households"] if h["plot"]}


def evidence_for_call(items: list[dict], tool: str, args: dict, cluster_id: str, cells: dict[str, str]) -> list[str]:
    """Evidence ids that a specific tool call actually backs (so citations can't over-reach)."""
    if tool == "get_household_cluster":
        return [i["evidenceId"] for i in items if i["kind"] == "plot"]
    if tool == "get_rainfall_evidence":
        key = cells.get(args.get("plot_id") or "") or args.get("cluster_id") or cluster_id
        return [i["evidenceId"] for i in items if i["kind"] in ("rainfall", "forecast")
                and i["evidenceId"].split(":")[1] == key]
    if tool == "get_crop_context":
        crop = args.get("crop")
        return [i["evidenceId"] for i in items if i["kind"] == "crop_calendar" and (not crop or f":{crop}:" in i["evidenceId"])]
    if tool == "get_pest_reports":
        return [i["evidenceId"] for i in items if i["kind"] == "pest_report"]
    return []


def build_evidence(conn: sqlite3.Connection, cluster_id: str) -> list[dict] | None:
    c = cluster_row(conn, cluster_id)
    if c is None:
        return None
    today = as_of_date(conn, None)
    items: list[dict] = []

    hh = tools.get_household_cluster(conn, cluster_id)["households"]
    for h in hh:
        pid = plot_id(h["household_id"])
        bits = [f"{h['area_ha']} ha {h['crop']}", f"variety {h['variety'] or 'not recorded'}",
                f"soil {h['soil_type'] or 'not recorded'}, drainage {h['drainage'] or 'not recorded'}",
                "irrigated" if h["has_irrigation"] else "rain-fed",
                f"status {h['planting_status']}"]
        if h["planting_status"] == "planted":
            bits.append(f"planted {h['planting_date']}")
        else:
            bits.append(f"planned planting {h['planned_planting_date'] or 'not recorded'}")
            bits.append("seed in hand: " + {True: "yes", False: "no", None: "not recorded"}[h["seed_in_hand"]])
        pl = h.get("plot") or {}
        if pl:
            bits.append(f"location: {pl['location_precision']}, {pl['verification_level']} (confidence {pl['location_confidence']})")
            if pl["area_check"] not in ("consistent", "not_checkable"):
                bits.append(f"area {pl['area_check']}")
        items.append(_item(f"plot:{pid}", "plot", f"Plot {pid} and household record",
                           f"{h['household_id']}; " + "; ".join(bits) + ".",
                           f"{h['planting_date']}T00:00:00Z" if h["planting_date"] else None,
                           "Synthetic household registry", pid,
                           "Synthetic test record" + (f"; missing: {', '.join(h['missing_fields'])}"
                                                      if h["missing_fields"] else "")))

    targets = [(None, cluster_id, f"cluster {cluster_id}")]
    for cell in sorted(set(plot_cells(conn, cluster_id).values())):
        pid = next(p for p, c in plot_cells(conn, cluster_id).items() if c == cell)
        targets.append((pid, cell, f"grid cell {cell}"))
    for pid, key, label in targets:
        r = tools.get_rainfall_evidence(conn, cluster_id=cluster_id, plot_id=pid)
        o, f = r["observed"], r["forecast"]
        dry = o["current_dry_spell_days"]

        def mm(t):
            return "no data" if t["mm"] is None else f"{t['mm']} mm"
        parts = [f"Last 7 d: {mm(o['total_last_7d'])} ({o['total_last_7d']['days_with_data']}/7 days with data)",
                 f"last 14 d: {mm(o['total_last_14d'])}",
                 f"current dry spell {dry} d" if dry is not None else "current dry spell unknown (no observation on the as-of date)",
                 f"last observation {o['last_observation_date'] or 'none'}"]
        if o["max_3day_total"]:
            m = o["max_3day_total"]
            parts.append(f"strongest 3-day total {m['mm']} mm ({m['from']} to {m['to']})")
        if o["missing_days"]:
            parts.append(f"{len(o['missing_days'])} missing day(s) in the 21-day window")
        parts.append(f"forecast first wet day {f['first_wet_day'] or 'none in window'}" if f["available"] else "no forecast available")
        res = r["location"]["resolution_note"]
        src = (r["sources"]["observed"] or "no observations")
        items.append(_item(f"rainfall:{key}:{today}", "rainfall", f"Rainfall · {label} · as of {today}",
                           "; ".join(parts) + f". {res}",
                           f"{o['last_observation_date']}T00:00:00Z" if o["last_observation_date"] else None,
                           f"Rainfall source: {src}", f"rainfall:{key}:{today}",
                           f"Test data; sufficiency: {r['evidence_sufficiency']}"
                           + (f" ({'; '.join(r['sufficiency_reasons'])})" if r["sufficiency_reasons"] else "")))
        if f["available"]:
            wet = [d for d in f["daily"] if d["rain_probability"] >= 0.5]
            items.append(_item(f"forecast:{key}:{f['issued_on']}", "forecast",
                               f"Forecast · {label} · issued {f['issued_on']}",
                               f"Consecutive dry days ahead: {f['consecutive_dry_days_ahead']}; first wet day: "
                               f"{f['first_wet_day'] or 'none'}; days with rain probability >= 50%: {len(wet)}.",
                               f"{f['issued_on']}T00:00:00Z", f"Forecast source: {r['sources']['forecast']}",
                               f"forecast:{key}:{f['issued_on']}", "Test data; not an operational forecast"))

    for crop in sorted({h["crop"] for h in hh}):
        cc = tools.get_crop_context(conn, crop, cluster_id)
        if cc["calendar_status"] == "no_calendar_data":
            continue
        s = cc["relevant_season"]
        items.append(_item(f"crop_calendar:{cluster_id}:{crop}:{s['season']}", "crop_calendar",
                           f"{crop} planting window · {c['commune']} ({s['season']})",
                           f"{s['window_start']} to {s['window_end']} ({s['status']}); onset {s['onset_rule']}; "
                           f"max safe dry spell {s['max_safe_dry_spell_days']} d; establishment {s['establishment_days']} d.",
                           None, "Synthetic crop calendar", f"{cluster_id}:{crop}:{s['season']}",
                           "Synthetic test rule; validate with the local extension service") | {"crop": crop})

    for p in tools.get_pest_reports(conn, cluster_id, since_days=60)["reports"]:
        items.append(_item(f"pest_report:{p['report_id']}", "pest_report",
                           f"{p['pest']} · {p['severity']} · {p['crop']}",
                           f"{p['fields_affected']} of {p['fields_scouted']} scouted fields affected; stage {p['growth_stage'] or 'n/a'}.",
                           f"{p['report_date']}T00:00:00Z", "Synthetic scout report", p["report_id"],
                           "Synthetic test report; not verified") | {"crop": p["crop"]})
    return items


def filter_for_tools(items: Iterable[dict], tool_names: Iterable[str]) -> list[dict]:
    kinds = set().union(*(KIND_BY_TOOL.get(t, set()) for t in tool_names)) if tool_names else set()
    return [i for i in items if i["kind"] in kinds]


SOURCE_SUMMARY = [
    "Plot and household records: synthetic registry (SQLite), fake farmer IDs",
    "Rainfall: synthetic gauge series; gaps and staleness are reported, never filled in",
    "Crop calendar: synthetic rule set; validate with the local extension service",
    "Pest reports: synthetic scout reports; absence of a report is not absence of pests",
    "Forecast: synthetic fixture; not AccuWeather and not operational",
]
