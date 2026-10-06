"""Synthetic Benin dataset. ALL data here is fabricated for development.

Fictional reference date: 2026-04-10 ("as_of_date" in the meta table).

Scenarios (designed to produce both positive and negative recommendations):
  GLZ-001  False start of season: heavy rain 31 Mar-2 Apr, then dry since; forecast dry until ~17 Apr.
           Mix of planned dates, irrigation, already-planted fields, crops, and missing fields.
  GLZ-002  Rain-station outage: observations stop 19 Mar, no forecast -> evidence is INSUFFICIENT.
  ZGB-001  Established, sustained rains and wet forecast -> planting is fine.
  KAN-001  Northern single-season zone; it is far too early (window opens 20 May).
"""
from __future__ import annotations

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from .. import config

AS_OF = date(2026, 4, 10)
SCHEMA = Path(__file__).with_name("schema.sql")


def _daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _farmer_codes(n: int, rng: random.Random) -> list[str]:
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    codes: set[str] = set()
    while len(codes) < n:
        codes.add("FRM-" + "".join(rng.choice(alphabet) for _ in range(4)))
    return sorted(codes)


CLUSTERS = [
    ("GLZ-001", "Glazoué cluster 1", "Collines", "Glazoué", "transition_bimodal", 7.97, 2.24),
    ("GLZ-002", "Glazoué cluster 2", "Collines", "Glazoué", "transition_bimodal", 7.99, 2.30),
    ("ZGB-001", "Zogbodomey cluster 1", "Zou", "Zogbodomey", "coastal_bimodal", 6.95, 2.30),
    ("KAN-001", "Kandi cluster 1", "Alibori", "Kandi", "sudanian_unimodal", 11.13, 2.94),
]

# (crop, agro_zone, season, start MM-DD, end MM-DD, onset_mm_3d, max_dry_spell_days, establishment_days, notes)
CALENDAR = [
    ("maize", "transition_bimodal", "major", "03-20", "04-30", 20, 7, 21,
     "Plant after onset: >=20 mm in 3 days not followed by a dry spell longer than 7 days."),
    ("maize", "transition_bimodal", "minor", "08-25", "09-20", 20, 7, 21, "Short-cycle varieties preferred."),
    ("maize", "coastal_bimodal", "major", "03-10", "04-20", 20, 7, 21, "Early onset zone."),
    ("maize", "coastal_bimodal", "minor", "09-01", "09-25", 20, 7, 21, None),
    ("maize", "sudanian_unimodal", "main", "05-20", "07-10", 25, 7, 21, "Single season; sowing before late May is risky."),
    ("cassava", "transition_bimodal", "major", "03-15", "05-31", 15, 21, 30, "Cuttings tolerate longer dry spells."),
    ("cowpea", "transition_bimodal", "major", "04-01", "05-15", 15, 7, 14, None),
]

VARIETIES = [
    ("maize", "extra-early-OPV", 80, "medium"),
    ("maize", "intermediate-OPV", 95, "medium"),
    ("maize", "hybrid-medium", 110, "low"),
    ("cassava", "local-cuttings", 300, "high"),
    ("cowpea", "early-cowpea", 65, "high"),
]


def _rain_glz001() -> dict[date, float | None]:
    r: dict[date, float | None] = {}
    rng = random.Random(1)
    for d in _daterange(date(2026, 3, 1), AS_OF):
        r[d] = round(rng.choice([0, 0, 0, 0, 0.2, 0.6]), 1)
    r[date(2026, 3, 12)] = 6.0
    r[date(2026, 3, 13)] = 4.0
    r[date(2026, 3, 31)] = 14.0
    r[date(2026, 4, 1)] = 28.0
    r[date(2026, 4, 2)] = 9.0
    for d in _daterange(date(2026, 4, 3), AS_OF):
        r[d] = 0.0 if d.day % 3 else 0.4
    r[date(2026, 3, 24)] = None  # station gap
    r[date(2026, 3, 25)] = None
    return r


def _rain_zgb001() -> dict[date, float | None]:
    r = {d: 0.0 for d in _daterange(date(2026, 3, 1), AS_OF)}
    for d, mm in [("03-28", 12), ("03-31", 25), ("04-01", 30), ("04-03", 18),
                  ("04-05", 22), ("04-07", 14), ("04-09", 20)]:
        r[date(2026, int(d[:2]), int(d[3:]))] = float(mm)
    return r


def _rain_kan001() -> dict[date, float | None]:
    r = {d: 0.0 for d in _daterange(date(2026, 3, 1), AS_OF)}
    r[date(2026, 4, 8)] = 6.0
    return r


def _rain_glz002() -> dict[date, float | None]:
    rng = random.Random(2)
    return {d: round(rng.choice([0, 0, 0.2, 1.0]), 1) for d in _daterange(date(2026, 3, 1), date(2026, 3, 19))}


def _forecast(cluster: str) -> list[tuple]:
    out = []
    for i in range(1, 15):
        d = AS_OF + timedelta(days=i)
        if cluster == "GLZ-001":
            wet = d >= date(2026, 4, 18)
            mm, p = (round(12 + 2 * (d.day - 18), 1), 0.7) if wet else (0.0 if i % 2 else 1.0, 0.1 if i % 2 else 0.2)
        elif cluster == "ZGB-001":
            mm, p = (15.0, 0.8) if i % 2 else (5.0, 0.6)
        else:  # KAN-001
            mm, p = (0.0, 0.05)
        out.append((cluster, d.isoformat(), mm, p, AS_OF.isoformat(), "synthetic-forecast"))
    return out


# (suffix, crop, variety, area, soil, drainage, irrigated, status, planned, planted, seed_in_hand)
H = {
    "GLZ-001": [
        ("001", "maize", "intermediate-OPV", 1.5, "loam", "good", 0, "not_planted", "2026-04-12", None, 1),
        ("002", "maize", "extra-early-OPV", 0.8, "sandy", "good", 0, "not_planted", "2026-04-14", None, 1),
        ("003", "maize", "intermediate-OPV", 2.0, "clay", "moderate", 0, "not_planted", "2026-04-20", None, 1),
        ("004", "maize", "intermediate-OPV", 1.0, "loam", "good", 1, "not_planted", "2026-04-11", None, 1),
        ("005", "maize", "intermediate-OPV", 1.2, "loam", "good", 0, "planted", None, "2026-04-03", 1),
        ("006", "maize", "hybrid-medium", 0.9, "sandy", "good", 0, "planted", None, "2026-04-05", 1),
        ("007", "maize", None, 1.1, "loam", "moderate", 0, "not_planted", None, None, None),
        ("008", "cassava", "local-cuttings", 1.4, "loam", "good", 0, "not_planted", "2026-04-12", None, 1),
        ("009", "maize", "intermediate-OPV", 1.3, "clay", "poor", 0, "not_planted", "2026-04-13", None, 1),
        ("010", "cowpea", "early-cowpea", 0.5, "sandy", "good", 0, "planted", None, "2026-04-04", 1),
        ("011", "maize", "hybrid-medium", 1.7, "loam", "moderate", 0, "not_planted", "2026-04-16", None, 0),
        ("012", "maize", "extra-early-OPV", 0.7, "loam", "good", 0, "not_planted", "2026-04-18", None, 1),
    ],
    "GLZ-002": [
        ("001", "maize", "intermediate-OPV", 1.0, "loam", "good", 0, "not_planted", "2026-04-12", None, 1),
        ("002", "maize", "extra-early-OPV", 0.9, "sandy", "good", 0, "not_planted", "2026-04-15", None, 1),
        ("003", "maize", "intermediate-OPV", 1.6, "clay", "moderate", 0, "planted", None, "2026-04-02", 1),
        ("004", "maize", "intermediate-OPV", 1.2, "loam", "good", 0, "not_planted", "2026-04-13", None, 1),
    ],
    "ZGB-001": [
        ("001", "maize", "intermediate-OPV", 1.8, "loam", "good", 0, "not_planted", "2026-04-12", None, 1),
        ("002", "maize", "extra-early-OPV", 1.0, "sandy", "good", 0, "not_planted", "2026-04-13", None, 1),
        ("003", "maize", "hybrid-medium", 2.2, "clay", "moderate", 0, "not_planted", "2026-04-15", None, 1),
        ("004", "maize", "intermediate-OPV", 1.1, "loam", "good", 0, "planted", None, "2026-04-04", 1),
        ("005", "maize", "intermediate-OPV", 0.9, "loam", "poor", 0, "not_planted", "2026-04-11", None, 1),
    ],
    "KAN-001": [
        ("001", "maize", "intermediate-OPV", 2.5, "gravelly", "good", 0, "not_planted", "2026-04-15", None, 1),
        ("002", "maize", "extra-early-OPV", 1.5, "loam", "good", 0, "not_planted", "2026-05-25", None, 1),
        ("003", "maize", "hybrid-medium", 3.0, "loam", "moderate", 0, "not_planted", "2026-06-05", None, 1),
        ("004", "maize", "intermediate-OPV", 2.0, "sandy", "good", 0, "not_planted", None, None, None),
    ],
}

# (cluster, date, pest, crop, severity, scouted, affected, stage)
PESTS = [
    ("GLZ-001", "2026-04-03", "fall armyworm", "maize", "low", 10, 1, "VE-V1"),
    ("GLZ-001", "2026-04-07", "fall armyworm", "maize", "moderate", 12, 4, "V1-V2"),
    ("GLZ-001", "2026-04-09", "fall armyworm", "maize", "moderate", 15, 6, "V2"),
    ("GLZ-001", "2026-03-20", "stem borer", "maize", "low", 8, 0, "pre-planting"),
    ("ZGB-001", "2026-04-08", "fall armyworm", "maize", "low", 10, 1, "V1"),
    ("KAN-001", "2026-04-02", "fall armyworm", "maize", "low", 5, 0, "off-season volunteers"),
]


def seed(db_path: Path | str | None = None, force: bool = True) -> Path:
    path = Path(db_path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not force:
            raise FileExistsError(path)
        path.unlink()
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA.read_text())
    conn.execute("INSERT INTO meta VALUES ('as_of_date', ?)", (AS_OF.isoformat(),))
    conn.execute("INSERT INTO meta VALUES ('data_provenance', 'SYNTHETIC - fabricated for development')")
    conn.executemany("INSERT INTO clusters VALUES (?,?,?,?,?,?,?)", CLUSTERS)
    conn.executemany("INSERT INTO crop_calendar VALUES (?,?,?,?,?,?,?,?,?)", CALENDAR)
    conn.executemany("INSERT INTO crop_varieties VALUES (?,?,?,?)", VARIETIES)

    n = sum(len(v) for v in H.values())
    codes = iter(_farmer_codes(n, random.Random(42)))
    rows = []
    for cid, hs in H.items():
        for s, crop, var, area, soil, drn, irr, st, plan, plant, seed_ in hs:
            rows.append((f"HH-{cid.replace('-', '')}-{s}", next(codes), cid, crop, var, area, soil, drn,
                         irr, st, plan, plant, seed_))
    conn.executemany("INSERT INTO households VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)

    for cid, series in [("GLZ-001", _rain_glz001()), ("GLZ-002", _rain_glz002()),
                        ("ZGB-001", _rain_zgb001()), ("KAN-001", _rain_kan001())]:
        conn.executemany(
            "INSERT INTO rainfall_observations VALUES (?,?,?,?)",
            [(cid, d.isoformat(), mm, "synthetic-gauge") for d, mm in series.items() if mm is not None],
        )
    for cid in ("GLZ-001", "ZGB-001", "KAN-001"):  # GLZ-002 deliberately has no forecast
        conn.executemany("INSERT INTO rainfall_forecast VALUES (?,?,?,?,?,?)", _forecast(cid))

    conn.executemany(
        "INSERT INTO pest_reports VALUES (?,?,?,?,?,?,?,?,?,?)",
        [(f"PR-{i:03d}", c, d, p, cr, sev, sc, af, stg, f"SCOUT-{(i % 3) + 1}")
         for i, (c, d, p, cr, sev, sc, af, stg) in enumerate(PESTS, 1)],
    )
    conn.commit()
    conn.close()
    return path
