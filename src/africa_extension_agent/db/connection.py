from __future__ import annotations

import sqlite3
from pathlib import Path

from .. import config


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    p = Path(path or config.DB_PATH)
    if not p.exists():
        raise FileNotFoundError(f"Database not found at {p}. Run: extension-agent seed")
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def connect_readonly(path: Path | str | None = None) -> sqlite3.Connection:
    """Read-only handle for the domain tools. Audit writes use a separate connection."""
    p = Path(path or config.DB_PATH).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Database not found at {p}. Run: extension-agent seed")
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn
