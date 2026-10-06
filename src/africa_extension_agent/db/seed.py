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

from .. import config, geo

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
    ("GLZ-002", "Glazoué cluster 2", "Collines", "Glazoué", "transition_bimodal", 7.99, 2.40),
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
    conn.executescript(SCHEMA.with_name("schema_geo.sql").read_text())
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
    _seed_geo(conn)
    conn.commit()
    conn.close()
    return path


# --- plot geometry, field candidates and plot-level weather (all synthetic) -------------------------------
# (suffix: (lat, lon, polygon_ha, geometry_source, verification_level, gps_accuracy_m, tenure))
GLZ001_PLOTS = {
    "001": (7.9720, 2.2300, 1.45, "officer_gps", "officer_surveyed", 4.0, "customary"),
    "002": (7.9735, 2.2345, 0.85, "satellite_field", "officer_matched", None, "customary"),
    "003": (7.9680, 2.2420, 2.10, "satellite_field", "satellite_candidate", None, "unknown"),
    "004": (7.9710, 2.2360, 0.98, "officer_gps", "officer_surveyed", 5.0, "leased"),
    "005": (7.9750, 2.2280, 1.15, "satellite_field", "officer_matched", None, "customary"),
    "006": (7.9690, 2.2310, 0.92, "satellite_field", "officer_matched", None, "sharecropped"),
    "008": (7.9760, 2.2390, 1.38, "satellite_field", "officer_matched", None, "customary"),
    "009": (7.9710, 2.2640, 1.30, "officer_gps", "officer_surveyed", 6.0, "certificate"),
    "010": (7.9660, 2.2440, 0.52, "satellite_field", "officer_matched", None, "customary"),
    "011": (7.9740, 2.2690, 1.65, "satellite_field", "officer_matched", None, "customary"),
    "012": (7.9700, 2.2610, 1.35, "satellite_field", "satellite_candidate", None, "unknown"),  # area mismatch (declared 0.7)
}
# (candidate suffix, lat, lon, ha)
CANDIDATES = [("0001", 7.9705, 2.2395, 1.05), ("0002", 7.9712, 2.2410, 0.40), ("0003", 7.9690, 2.2370, 1.90),
              ("0004", 7.9702, 2.2612, 0.72), ("0005", 7.9683, 2.2418, 1.95), ("0006", 7.9755, 2.2650, 0.60)]


def _plot_id(household_id: str) -> str:
    return "PL-" + household_id.removeprefix("HH-")


def _cell(conn: sqlite3.Connection, lat: float, lon: float) -> str:
    c = geo.grid_cell(lat, lon)
    conn.execute("INSERT OR IGNORE INTO weather_cells VALUES (?,?,?,?)", (c["cell_id"], c["center_lat"], c["center_lon"], geo.GRID_STEP))
    return c["cell_id"]


def _seed_geo(conn: sqlite3.Connection) -> None:
    now = AS_OF.isoformat() + "T00:00:00+00:00"
    clusters = {r[0]: (r[1], r[2], r[3]) for r in conn.execute("SELECT cluster_id, latitude, longitude, commune FROM clusters")}
    for hid, cid in conn.execute("SELECT household_id, cluster_id FROM households ORDER BY household_id").fetchall():
        spec = GLZ001_PLOTS.get(hid.rsplit("-", 1)[1]) if cid == "GLZ-001" else None
        clat, clon, commune = clusters[cid]
        if spec:
            lat, lon, ha, src, level, acc, tenure = spec
            g = geo.summarize(geo.square_polygon(lat, lon, ha, jitter=0.03))
            row = (_plot_id(hid), hid, g["geojson"], g["lat"], g["lon"], g["area_ha"], src, level, acc,
                   AS_OF.isoformat(), tenure, f"{commune} (village A)", commune, None, None, None)
            if level == "officer_matched":
                row = row[:-2] + ("Officer demo", now)
        else:  # no geometry known: located only to the village/cluster centroid
            row = (_plot_id(hid), hid, None, clat, clon, None, "village_only", "declared", None, None,
                   "unknown", f"{commune} (village centroid)", commune, None, None, None)
        conn.execute("INSERT INTO plots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", row)
    for suf, lat, lon, ha in CANDIDATES:
        g = geo.summarize(geo.square_polygon(lat, lon, ha, jitter=0.05))
        conn.execute("INSERT INTO field_candidates VALUES (?,?,?,?,?,?,?,?,?)",
                     (f"FC-GLZ-{suf}", "synthetic-fields-demo", suf, g["geojson"], g["lat"], g["lon"], g["area_ha"], 0.7, now))

    # weather grid: observed + forecast per cell
    stamp = now
    def put(cell, series, fc_cluster):
        for d, mm in series.items():
            if mm is not None:
                conn.execute("INSERT OR REPLACE INTO weather_obs_grid VALUES (?,?,?,?,?)", (cell, d.isoformat(), mm, "synthetic-grid", stamp))
        if fc_cluster:
            for (_c, d, mm, p, issued, _src) in _forecast(fc_cluster):
                conn.execute("INSERT OR REPLACE INTO weather_fc_grid VALUES (?,?,?,?,?,?,?)", (cell, d, mm, p, issued, "synthetic-grid-forecast", stamp))
    series = {"GLZ-001": _rain_glz001(), "GLZ-002": _rain_glz002(), "ZGB-001": _rain_zgb001(), "KAN-001": _rain_kan001()}
    cell_a = _cell(conn, 7.972, 2.235)
    put(cell_a, series["GLZ-001"], "GLZ-001")
    cell_b = _cell(conn, 7.971, 2.265)           # 5 km east: a local storm on 8-9 April reached this cell only
    sb = dict(series["GLZ-001"]); sb[date(2026, 4, 8)] = 24.0; sb[date(2026, 4, 9)] = 6.0; sb[date(2026, 4, 10)] = 0.0
    put(cell_b, sb, "GLZ-001")
    for cid in ("GLZ-002", "ZGB-001", "KAN-001"):
        put(_cell(conn, clusters[cid][0], clusters[cid][1]), series[cid], cid if cid != "GLZ-002" else None)
    for (pid, lat, lon) in conn.execute("SELECT plot_id, centroid_lat, centroid_lon FROM plots").fetchall():
        _cell(conn, lat, lon)  # every plot resolves to a known cell, with or without data
