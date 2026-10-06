"""Owner identity lives in its OWN database file. The MCP server, tools and agent never import or open it.
Revealing an identity is an explicit, logged action."""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import config

PII_DB = Path(os.environ.get("EXTENSION_AGENT_PII_DB", Path(config.DB_PATH).parent / "identity.sqlite"))
SCHEMA = """
CREATE TABLE IF NOT EXISTS farmer_identity (
  farmer_code TEXT PRIMARY KEY, external_id TEXT UNIQUE, full_name TEXT, phone TEXT,
  consent_status TEXT NOT NULL, consent_recorded_on TEXT, source TEXT);
CREATE TABLE IF NOT EXISTS identity_access_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts_utc TEXT NOT NULL, accessor TEXT NOT NULL, farmer_code TEXT NOT NULL, purpose TEXT NOT NULL);
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    p = Path(path or PII_DB)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def reveal(farmer_code: str, accessor: str, purpose: str, path: Path | str | None = None) -> dict | None:
    if len(accessor.strip()) < 2 or len(purpose.strip()) < 5:
        raise ValueError("accessor name and a purpose are required")
    conn = connect(path)
    try:
        row = conn.execute("SELECT * FROM farmer_identity WHERE farmer_code=?", (farmer_code,)).fetchone()
        conn.execute("INSERT INTO identity_access_log (ts_utc, accessor, farmer_code, purpose) VALUES (?,?,?,?)",
                     (datetime.now(timezone.utc).isoformat(timespec="seconds"), accessor.strip(), farmer_code, purpose.strip()))
        conn.commit()
        return dict(row) if row and row["consent_status"] == "granted" else None
    finally:
        conn.close()
