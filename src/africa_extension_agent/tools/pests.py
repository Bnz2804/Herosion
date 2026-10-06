"""get_pest_reports: WHAT pests scouts have observed recently (incidence + sample-size caveats)."""
from __future__ import annotations

import sqlite3
from datetime import timedelta

from ._util import as_of_date, cluster_row, not_found

MIN_FIELDS_FOR_CONFIDENCE = 30


def get_pest_reports(conn: sqlite3.Connection, cluster_id: str, crop: str | None = None,
                     since_days: int = 30, as_of: str | None = None) -> dict:
    if cluster_row(conn, cluster_id) is None:
        return not_found(cluster_id)
    today = as_of_date(conn, as_of)
    since = today - timedelta(days=max(1, min(since_days, 180)))
    q = "SELECT * FROM pest_reports WHERE cluster_id=? AND report_date BETWEEN ? AND ?"
    args: list = [cluster_id, since.isoformat(), today.isoformat()]
    if crop:
        q += " AND lower(crop)=lower(?)"
        args.append(crop)
    rows = conn.execute(q + " ORDER BY report_date", args).fetchall()

    agg: dict[str, dict] = {}
    for r in rows:
        a = agg.setdefault(r["pest"], {"pest": r["pest"], "reports": 0, "fields_scouted": 0,
                                       "fields_affected": 0, "series": []})
        a["reports"] += 1
        a["fields_scouted"] += r["fields_scouted"]
        a["fields_affected"] += r["fields_affected"]
        a["series"].append((r["report_date"], r["fields_affected"] / r["fields_scouted"], r["severity"]))
    pests = []
    for a in agg.values():
        s = a.pop("series")
        a["incidence_pct"] = round(100 * a["fields_affected"] / a["fields_scouted"], 1)
        a["latest_report"] = {"date": s[-1][0], "incidence_pct": round(100 * s[-1][1], 1), "severity": s[-1][2]}
        a["trend"] = ("rising" if s[-1][1] > s[0][1] else "falling" if s[-1][1] < s[0][1] else "flat") \
            if len(s) >= 2 else "unknown (single report)"
        a["confidence_note"] = ("small sample (<%d fields scouted)" % MIN_FIELDS_FOR_CONFIDENCE
                                if a["fields_scouted"] < MIN_FIELDS_FOR_CONFIDENCE else "adequate sample")
        pests.append(a)
    return {
        "found": True, "cluster_id": cluster_id, "window": [since.isoformat(), today.isoformat()],
        "crop_filter": crop, "n_reports": len(rows), "by_pest": pests,
        "reports": [{k: r[k] for k in ("report_id", "report_date", "pest", "crop", "severity",
                                        "fields_scouted", "fields_affected", "growth_stage")} for r in rows],
        "summary": f"{len(rows)} pest report(s) for {cluster_id} in last {since_days} d"
                   + (f" ({', '.join(f'{p['pest']} {p['incidence_pct']}%' for p in pests)})" if pests
                      else " - no reports (absence of reports is not evidence of absence of pests)"),
    }
