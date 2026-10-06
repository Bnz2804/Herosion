"""get_rainfall_evidence: WHAT the weather has done and is forecast to do (no crop interpretation).

Two bases:
  * plot_id given  -> the 5 km grid cell that contains the plot's centroid (location precision is reported)
  * cluster_id only -> the cluster's own series (legacy/cluster-level)
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from .. import geo
from ._util import as_of_date, cluster_row, not_found
from .plots import describe, plot_for

RAIN_DAY_MM = 1.0


def _mm(v) -> str:
    return "no data" if v is None else f"{v} mm"


def _load(conn, basis, key, start, today, forecast_days):
    """Return (obs {iso: mm}, last_obs_iso, forecast rows, obs_source, fc_source)."""
    if basis == "cell":
        o_q = "SELECT obs_date d, rainfall_mm mm, source FROM weather_obs_grid WHERE cell_id=? AND obs_date BETWEEN ? AND ?"
        l_q = "SELECT MAX(obs_date) m FROM weather_obs_grid WHERE cell_id=? AND obs_date<=?"
        f_q = ("SELECT forecast_date AS forecast_date, expected_mm, rain_probability, issued_on, source FROM weather_fc_grid "
               "WHERE cell_id=? AND forecast_date>? AND forecast_date<=? ORDER BY forecast_date")
    else:
        o_q = "SELECT obs_date d, rainfall_mm mm, source FROM rainfall_observations WHERE cluster_id=? AND obs_date BETWEEN ? AND ?"
        l_q = "SELECT MAX(obs_date) m FROM rainfall_observations WHERE cluster_id=? AND obs_date<=?"
        f_q = ("SELECT forecast_date, expected_mm, rain_probability, issued_on, source FROM rainfall_forecast "
               "WHERE cluster_id=? AND forecast_date>? AND forecast_date<=? ORDER BY forecast_date")
    rows = conn.execute(o_q, (key, start.isoformat(), today.isoformat())).fetchall()
    obs = {r["d"]: r["mm"] for r in rows}
    last = conn.execute(l_q, (key, today.isoformat())).fetchone()["m"]
    fc = conn.execute(f_q, (key, today.isoformat(), (today + timedelta(days=forecast_days)).isoformat())).fetchall()
    return obs, last, fc, (rows[0]["source"] if rows else None), (fc[0]["source"] if fc else None)


def get_rainfall_evidence(conn: sqlite3.Connection, cluster_id: str | None = None, plot_id: str | None = None,
                          as_of: str | None = None, lookback_days: int = 21, forecast_days: int = 14) -> dict:
    location: dict
    if plot_id:
        prow = plot_for(conn, plot_id)
        if prow is None:
            return {"found": False, "plot_id": plot_id, "summary": f"No plot '{plot_id}' in the database.",
                    "note": "Do not guess data for this plot."}
        cluster_id = prow["cluster_id"]
        d = describe(prow)
        cell = geo.grid_cell(prow["centroid_lat"], prow["centroid_lon"])
        dist = round(geo.haversine_km(prow["centroid_lat"], prow["centroid_lon"], cell["center_lat"], cell["center_lon"]), 2)
        basis, key = "cell", cell["cell_id"]
        location = {"basis": "plot_grid_cell", "plot_id": plot_id, "cell_id": cell["cell_id"],
                    "distance_to_cell_center_km": dist, "cell_size_km": 5.5,
                    "plot_verification_level": d["verification_level"], "location_confidence": d["location_confidence"],
                    "location_precision": d["location_precision"],
                    "resolution_note": "Grid-cell estimate (~5.5 km), not an on-farm gauge; rain can differ between nearby fields."}
    else:
        if not cluster_id or cluster_row(conn, cluster_id) is None:
            return not_found(cluster_id or "(none)")
        basis, key = "cluster", cluster_id
        location = {"basis": "cluster_series", "cluster_id": cluster_id,
                    "resolution_note": "Cluster-level series; not specific to any plot."}
    if cluster_row(conn, cluster_id) is None:
        return not_found(cluster_id)

    today = as_of_date(conn, as_of)
    lookback_days = max(7, min(lookback_days, 60))
    forecast_days = max(1, min(forecast_days, 14))
    start = today - timedelta(days=lookback_days - 1)
    obs, last_obs, fc, obs_src, fc_src = _load(conn, basis, key, start, today, forecast_days)
    days = [start + timedelta(days=i) for i in range(lookback_days)]
    missing = [d.isoformat() for d in days if d.isoformat() not in obs]

    def total(n: int):
        vals = [obs[x] for x in ((today - timedelta(days=i)).isoformat() for i in range(n)) if x in obs]
        return {"mm": round(sum(vals), 1) if vals else None, "days_with_data": len(vals), "days_requested": n}

    dry = 0
    for d in reversed(days):
        v = obs.get(d.isoformat())
        if v is None or v >= RAIN_DAY_MM:
            break
        dry += 1
    best = None
    for i in range(len(days) - 2):
        trip = [obs.get(days[i + k].isoformat()) for k in range(3)]
        if None in trip:
            continue
        s = sum(trip)
        if best is None or s > best["mm"]:
            best = {"mm": round(s, 1), "from": days[i].isoformat(), "to": days[i + 2].isoformat()}

    first_wet = next((r["forecast_date"] for r in fc if r["rain_probability"] >= 0.5 and r["expected_mm"] >= 5), None)
    dry_ahead = 0
    for r in fc:
        if r["rain_probability"] < 0.5:
            dry_ahead += 1
        else:
            break

    reasons = []
    lag = None
    if last_obs is None:
        reasons.append("no rainfall observations exist for this location")
    else:
        lag = (today - date.fromisoformat(last_obs)).days
        if lag > 3:
            reasons.append(f"latest observation is {last_obs}, {lag} days before as_of {today}")
    if missing:
        reasons.append(f"{len(missing)} observation day(s) missing in lookback window: {', '.join(missing)}")
    if not fc:
        reasons.append("no forecast available")
    stale = last_obs is None or (lag is not None and lag > 3)
    sufficiency = "insufficient" if stale else ("partial" if reasons else "sufficient")
    cur_dry = dry if last_obs == today.isoformat() else None

    return {
        "found": True, "cluster_id": cluster_id, "plot_id": plot_id, "as_of": today.isoformat(),
        "location": location,
        "sources": {"observed": obs_src, "forecast": fc_src},
        "observed": {
            "window": [start.isoformat(), today.isoformat()], "last_observation_date": last_obs,
            "missing_days": missing, "total_last_7d": total(7), "total_last_14d": total(14),
            "total_last_21d": total(min(21, lookback_days)), "current_dry_spell_days": cur_dry,
            "rain_day_threshold_mm": RAIN_DAY_MM, "max_3day_total": best,
        },
        "forecast": {
            "available": bool(fc), "issued_on": fc[0]["issued_on"] if fc else None, "days_covered": len(fc),
            "consecutive_dry_days_ahead": dry_ahead if fc else None, "first_wet_day": first_wet,
            "daily": [{"date": r["forecast_date"], "expected_mm": r["expected_mm"],
                       "rain_probability": r["rain_probability"]} for r in fc],
        },
        "evidence_sufficiency": sufficiency, "sufficiency_reasons": reasons,
        "summary": (f"{plot_id or cluster_id}" + (f" [cell {key}]" if plot_id else "") +
                    f": last 7d {_mm(total(7)['mm'])}, dry spell {str(cur_dry) + ' d' if cur_dry is not None else 'unknown'}, "
                    f"forecast first wet day {first_wet or 'none in window'}; evidence {sufficiency}."),
    }
