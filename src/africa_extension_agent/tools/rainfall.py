"""get_rainfall_evidence: WHAT the weather has done and is forecast to do (no crop interpretation)."""
from __future__ import annotations

import sqlite3
from datetime import timedelta

from ._util import as_of_date, cluster_row, not_found

RAIN_DAY_MM = 1.0


def _mm(v) -> str:
    return "no data" if v is None else f"{v} mm"


def get_rainfall_evidence(conn: sqlite3.Connection, cluster_id: str, as_of: str | None = None,
                          lookback_days: int = 21, forecast_days: int = 14) -> dict:
    if cluster_row(conn, cluster_id) is None:
        return not_found(cluster_id)
    today = as_of_date(conn, as_of)
    lookback_days = max(7, min(lookback_days, 60))
    forecast_days = max(1, min(forecast_days, 14))
    start = today - timedelta(days=lookback_days - 1)

    obs = {r["obs_date"]: r["rainfall_mm"] for r in conn.execute(
        "SELECT obs_date, rainfall_mm FROM rainfall_observations WHERE cluster_id=? AND obs_date BETWEEN ? AND ?",
        (cluster_id, start.isoformat(), today.isoformat()))}
    days = [start + timedelta(days=i) for i in range(lookback_days)]
    missing = [d.isoformat() for d in days if d.isoformat() not in obs]
    last_obs = conn.execute("SELECT MAX(obs_date) m FROM rainfall_observations WHERE cluster_id=? AND obs_date<=?",
                            (cluster_id, today.isoformat())).fetchone()["m"]

    def total(n: int):
        ds = [(today - timedelta(days=i)).isoformat() for i in range(n)]
        vals = [obs[d] for d in ds if d in obs]
        return {"mm": round(sum(vals), 1) if vals else None, "days_with_data": len(vals), "days_requested": n}

    # current dry spell: consecutive days (ending at last observed day) below RAIN_DAY_MM
    dry = 0
    for d in reversed(days):
        v = obs.get(d.isoformat())
        if v is None:
            break
        if v >= RAIN_DAY_MM:
            break
        dry += 1
    # strongest 3-day accumulation in window (complete triples only)
    best = None
    for i in range(len(days) - 2):
        trip = [obs.get(days[i + k].isoformat()) for k in range(3)]
        if None in trip:
            continue
        s = sum(trip)
        if best is None or s > best["mm"]:
            best = {"mm": round(s, 1), "from": days[i].isoformat(), "to": days[i + 2].isoformat()}

    fc = conn.execute(
        "SELECT * FROM rainfall_forecast WHERE cluster_id=? AND forecast_date>? AND forecast_date<=? ORDER BY forecast_date",
        (cluster_id, today.isoformat(), (today + timedelta(days=forecast_days)).isoformat())).fetchall()
    first_wet = next((r["forecast_date"] for r in fc if r["rain_probability"] >= 0.5 and r["expected_mm"] >= 5), None)
    dry_ahead = 0
    for r in fc:
        if r["rain_probability"] < 0.5:
            dry_ahead += 1
        else:
            break

    reasons = []
    if last_obs is None:
        reasons.append("no rainfall observations exist for this cluster")
    else:
        lag = (today - __import__("datetime").date.fromisoformat(last_obs)).days
        if lag > 3:
            reasons.append(f"latest observation is {last_obs}, {lag} days before as_of {today}")
    if missing:
        reasons.append(f"{len(missing)} observation day(s) missing in lookback window: {', '.join(missing)}")
    if len(missing) > lookback_days * 0.25:
        reasons.append(f"{len(missing)} of {lookback_days} lookback days missing")
    if not fc:
        reasons.append("no forecast available")
    sufficiency = "insufficient" if (last_obs is None or any("latest observation" in x for x in reasons)) \
        else ("partial" if reasons or missing else "sufficient")

    return {
        "found": True, "cluster_id": cluster_id, "as_of": today.isoformat(),
        "observed": {
            "window": [start.isoformat(), today.isoformat()],
            "last_observation_date": last_obs,
            "missing_days": missing,
            "total_last_7d": total(7), "total_last_14d": total(14), "total_last_21d": total(min(21, lookback_days)),
            "current_dry_spell_days": dry if last_obs == today.isoformat() else None,
            "rain_day_threshold_mm": RAIN_DAY_MM,
            "max_3day_total": best,
        },
        "forecast": {
            "available": bool(fc), "issued_on": fc[0]["issued_on"] if fc else None,
            "days_covered": len(fc),
            "consecutive_dry_days_ahead": dry_ahead if fc else None,
            "first_wet_day": first_wet,
            "daily": [{"date": r["forecast_date"], "expected_mm": r["expected_mm"],
                       "rain_probability": r["rain_probability"]} for r in fc],
        },
        "evidence_sufficiency": sufficiency,
        "sufficiency_reasons": reasons,
        "summary": f"{cluster_id}: last 7d {_mm(total(7)['mm'])}, dry spell "
                   f"{str(dry) + ' d' if last_obs == today.isoformat() else 'unknown'}, "
                   f"forecast first wet day {first_wet or 'none in window'}; evidence {sufficiency}.",
    }
