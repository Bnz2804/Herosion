"""Fetch plot-cell weather into SQLite. Pluggable provider; network failure keeps old data (never invents)."""
from __future__ import annotations

import json
import sqlite3
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from typing import Protocol

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"


class Provider(Protocol):
    name: str

    def fetch(self, lat: float, lon: float, today: date, past_days: int, forecast_days: int) -> dict: ...


class OpenMeteo:
    """Free model-based rainfall (past days = model analysis, NOT a gauge). Check Open-Meteo's terms for
    commercial/production use before relying on it."""
    name = "open-meteo"

    def fetch(self, lat, lon, today, past_days=14, forecast_days=14) -> dict:
        q = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "timezone": "Africa/Lagos",
                                    "daily": "precipitation_sum,precipitation_probability_max",
                                    "past_days": past_days, "forecast_days": forecast_days})
        with urllib.request.urlopen(f"{OPEN_METEO}?{q}", timeout=20) as r:
            d = json.loads(r.read())["daily"]
        obs, fc = [], []
        for day, mm, pr in zip(d["time"], d["precipitation_sum"], d.get("precipitation_probability_max") or [None] * len(d["time"])):
            if mm is None:
                continue
            (obs if date.fromisoformat(day) <= today else fc).append((day, mm) if date.fromisoformat(day) <= today else (day, mm, (pr or 0) / 100))
        return {"observed": obs, "forecast": fc, "issued_on": today.isoformat(),
                "source_obs": "open-meteo-model-analysis", "source_fc": "open-meteo-forecast"}


def sync(conn: sqlite3.Connection, provider: Provider, today: date | None = None, only_cells: set[str] | None = None,
         past_days: int = 14, forecast_days: int = 14) -> list[dict]:
    """Refresh every cell that has at least one plot. Returns a per-cell report."""
    today = today or datetime.now(timezone.utc).date()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cells = conn.execute("SELECT c.* FROM weather_cells c WHERE EXISTS (SELECT 1 FROM plots p "
                         "WHERE p.centroid_lat >= c.center_lat - c.step_deg/2 AND p.centroid_lat < c.center_lat + c.step_deg/2 "
                         "AND p.centroid_lon >= c.center_lon - c.step_deg/2 AND p.centroid_lon < c.center_lon + c.step_deg/2)").fetchall()
    report = []
    for c in cells:
        if only_cells and c["cell_id"] not in only_cells:
            continue
        try:
            res = provider.fetch(c["center_lat"], c["center_lon"], today, past_days, forecast_days)
        except Exception as exc:  # leave existing rows untouched
            report.append({"cell": c["cell_id"], "status": "error", "error": f"{type(exc).__name__}: {exc}"})
            continue
        with conn:
            conn.executemany("INSERT OR REPLACE INTO weather_obs_grid VALUES (?,?,?,?,?)",
                             [(c["cell_id"], d, mm, res["source_obs"], now) for d, mm in res["observed"]])
            conn.execute("DELETE FROM weather_fc_grid WHERE cell_id=?", (c["cell_id"],))
            conn.executemany("INSERT INTO weather_fc_grid VALUES (?,?,?,?,?,?,?)",
                             [(c["cell_id"], d, mm, p, res["issued_on"], res["source_fc"], now) for d, mm, p in res["forecast"]])
        report.append({"cell": c["cell_id"], "status": "ok", "observed": len(res["observed"]), "forecast": len(res["forecast"])})
    return report
