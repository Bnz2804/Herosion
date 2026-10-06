"""get_household_cluster: WHO is in the cluster and what do we know (and not know) about them."""
from __future__ import annotations

import sqlite3
from collections import Counter

from ._util import cluster_row, not_found

TRACKED_FIELDS = ["variety", "planned_planting_date", "seed_in_hand", "soil_type", "drainage"]


def get_household_cluster(conn: sqlite3.Connection, cluster_id: str, crop: str | None = None,
                          planting_status: str | None = None) -> dict:
    c = cluster_row(conn, cluster_id)
    if c is None:
        return not_found(cluster_id)
    q = "SELECT * FROM households WHERE cluster_id = ?"
    args: list = [cluster_id]
    if crop:
        q += " AND lower(crop) = lower(?)"
        args.append(crop)
    if planting_status:
        q += " AND planting_status = ?"
        args.append(planting_status)
    rows = conn.execute(q + " ORDER BY household_id", args).fetchall()

    households = []
    for r in rows:
        h = {k: r[k] for k in ("household_id", "farmer_code", "crop", "variety", "area_ha", "soil_type",
                               "drainage", "planting_status", "planned_planting_date", "planting_date")}
        h["has_irrigation"] = bool(r["has_irrigation"])
        h["seed_in_hand"] = None if r["seed_in_hand"] is None else bool(r["seed_in_hand"])
        # Missing fields are reported explicitly so the agent cannot silently assume values.
        h["missing_fields"] = [f for f in TRACKED_FIELDS
                               if r[f] is None and not (f == "planned_planting_date" and r["planting_status"] == "planted")]
        households.append(h)

    all_rows = conn.execute("SELECT crop, planting_status FROM households WHERE cluster_id = ?",
                            (cluster_id,)).fetchall()
    return {
        "found": True,
        "cluster": {k: c[k] for k in ("cluster_id", "name", "department", "commune", "agro_zone")},
        "filters_applied": {"crop": crop, "planting_status": planting_status},
        "cluster_totals": dict(Counter(f"{r['crop']}/{r['planting_status']}" for r in all_rows)),
        "households": households,
        "summary": f"{len(households)} household(s) returned for {cluster_id}"
                   f" (crop={crop or 'any'}, status={planting_status or 'any'}); "
                   f"{sum(1 for h in households if h['missing_fields'])} with missing fields.",
    }
