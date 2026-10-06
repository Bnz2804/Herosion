"""get_crop_context: WHEN is a crop agronomically meant to go in the ground (calendar + variety rules)."""
from __future__ import annotations

import sqlite3
from datetime import date

from ._util import as_of_date, cluster_row, not_found


def _md(year: int, mmdd: str) -> date:
    return date(year, int(mmdd[:2]), int(mmdd[3:]))


def get_crop_context(conn: sqlite3.Connection, crop: str, cluster_id: str, as_of: str | None = None) -> dict:
    c = cluster_row(conn, cluster_id)
    if c is None:
        return not_found(cluster_id)
    today = as_of_date(conn, as_of)
    zone = c["agro_zone"]
    rows = conn.execute("SELECT * FROM crop_calendar WHERE lower(crop)=lower(?) AND agro_zone=?",
                        (crop, zone)).fetchall()
    if not rows:
        return {"found": True, "cluster_id": cluster_id, "crop": crop, "agro_zone": zone,
                "calendar": [], "calendar_status": "no_calendar_data",
                "summary": f"No crop-calendar entry for {crop} in zone {zone}. Do not assume a planting window."}

    seasons, best = [], None
    for r in rows:
        s, e = _md(today.year, r["window_start"]), _md(today.year, r["window_end"])
        if s <= today <= e:
            status, delta = "inside_window", (e - today).days
        elif today < s:
            status, delta = "before_window", (s - today).days
        else:
            status, delta = "after_window", (today - e).days
        entry = {"season": r["season"], "window_start": s.isoformat(), "window_end": e.isoformat(),
                 "status": status, "days_delta": delta,
                 "onset_rule": f">= {r['onset_rain_mm']} mm in 3 days",
                 "onset_rain_mm_3d": r["onset_rain_mm"],
                 "max_safe_dry_spell_days": r["max_safe_dry_spell_days"],
                 "establishment_days": r["establishment_days"], "notes": r["notes"]}
        seasons.append(entry)
        rank = {"inside_window": 0, "before_window": 1, "after_window": 2}[status]
        if best is None or (rank, delta) < best[0]:
            best = ((rank, delta), entry)

    varieties = [dict(v) for v in conn.execute(
        "SELECT variety, maturity_days, drought_tolerance FROM crop_varieties WHERE lower(crop)=lower(?)", (crop,))]
    cur = best[1]
    return {
        "found": True, "cluster_id": cluster_id, "crop": crop, "agro_zone": zone, "as_of": today.isoformat(),
        "seasons": seasons, "relevant_season": cur, "calendar_status": cur["status"],
        "varieties": varieties,
        "summary": f"{crop} in {zone}: season '{cur['season']}' window {cur['window_start']}..{cur['window_end']} "
                   f"is {cur['status']} (delta {cur['days_delta']} d); onset {cur['onset_rule']}, "
                   f"max safe dry spell {cur['max_safe_dry_spell_days']} d.",
    }
