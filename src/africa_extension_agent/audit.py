"""Audit logging: every MCP tool call is recorded in SQLite (success or failure)."""
from __future__ import annotations

import functools
import hashlib
import json
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from . import config

SESSION_ENV = "EXTENSION_AGENT_SESSION"


def _writer() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def result_count(result: Any) -> int:
    """How many records a tool result contains (used for the workbench tool-call table)."""
    if not isinstance(result, dict) or result.get("found") is False:
        return 0
    if "households" in result:
        return len(result["households"])
    if "n_reports" in result:
        return result["n_reports"]
    if "observed" in result:
        return result["observed"]["total_last_21d"]["days_with_data"] + len(result["forecast"]["daily"])
    if "seasons" in result:
        return len(result["seasons"])
    return 1


def record(*, call_id: str, session_id: str, tool: str, arguments: dict, status: str,
           duration_ms: int, result: Any = None, error: str | None = None) -> None:
    sha = summary = None
    if result is not None:
        sha = hashlib.sha256(json.dumps(result, sort_keys=True, default=str).encode()).hexdigest()
        summary = result.get("summary") if isinstance(result, dict) else None
    conn = _writer()
    try:
        conn.execute(
            "INSERT INTO audit_log VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (call_id, session_id, datetime.now(timezone.utc).isoformat(timespec="milliseconds"), tool,
             json.dumps(arguments, sort_keys=True, default=str), status, duration_ms, sha, summary,
             result_count(result) if result is not None else None, error))
        conn.commit()
    finally:
        conn.close()


def audited(tool_name: str):
    """Wrap a domain function `fn(**kwargs) -> dict`. Adds `audit_call_id` to the returned dict
    so downstream conclusions can cite the exact logged call."""
    def deco(fn: Callable[..., dict]):
        @functools.wraps(fn)
        def wrapper(**kwargs):
            call_id = "call-" + uuid.uuid4().hex[:10]
            session = os.environ.get(SESSION_ENV) or "unscoped-" + uuid.uuid4().hex[:8]
            t0 = time.perf_counter()
            try:
                result = fn(**kwargs)
            except Exception as exc:  # log then surface to the caller
                record(call_id=call_id, session_id=session, tool=tool_name, arguments=kwargs, status="error",
                       duration_ms=int((time.perf_counter() - t0) * 1000), error=f"{type(exc).__name__}: {exc}")
                raise
            record(call_id=call_id, session_id=session, tool=tool_name, arguments=kwargs, status="ok",
                   duration_ms=int((time.perf_counter() - t0) * 1000), result=result)
            return {**result, "audit_call_id": call_id}
        return wrapper
    return deco


def read_log(session_id: str | None = None, limit: int = 50) -> list[dict]:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        if session_id:
            rows = conn.execute("SELECT * FROM audit_log WHERE session_id=? ORDER BY ts_utc", (session_id,))
        else:
            rows = conn.execute("SELECT * FROM audit_log ORDER BY ts_utc DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]
    finally:
        conn.close()
