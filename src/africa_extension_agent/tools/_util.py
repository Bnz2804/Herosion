from __future__ import annotations

import os
import sqlite3
from datetime import date


def as_of_date(conn: sqlite3.Connection, as_of: str | None) -> date:
    if as_of:
        return date.fromisoformat(as_of)
    mode = conn.execute("SELECT value FROM meta WHERE key='as_of_mode'").fetchone()
    if (mode and mode["value"] == "live") or os.environ.get("EXTENSION_AGENT_AS_OF") == "today":
        return date.today()
    row = conn.execute("SELECT value FROM meta WHERE key='as_of_date'").fetchone()
    return date.fromisoformat(row["value"])


def cluster_row(conn: sqlite3.Connection, cluster_id: str):
    return conn.execute("SELECT * FROM clusters WHERE cluster_id = ?", (cluster_id,)).fetchone()


def not_found(cluster_id: str) -> dict:
    return {"found": False, "cluster_id": cluster_id,
            "summary": f"No cluster '{cluster_id}' in the database.",
            "note": "Do not guess data for this cluster."}
