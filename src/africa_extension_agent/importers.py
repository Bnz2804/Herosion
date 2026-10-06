"""Load existing data: satellite/registry field polygons, and farmer+plot lists (CSV) with a quality report."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from . import geo, pii

SOURCE_LEVEL = {  # geometry_source -> verification_level assigned on import
    "cadastre_andf": "cadastral", "officer_gps": "officer_surveyed",
    "cooperative_file": "declared", "satellite_field": "satellite_candidate",
}


def _features(path: Path, bbox=None):
    suf = path.suffix.lower()
    if suf in (".geojson", ".json"):
        data = json.loads(path.read_text())
        yield from data["features"] if data.get("type") == "FeatureCollection" else [data]
    elif suf in (".geojsonl", ".ndjson", ".jsonl"):
        for line in path.read_text().splitlines():
            if line.strip():
                yield json.loads(line)
    elif suf == ".parquet":  # GeoParquet (WKB geometry); needs: pip install ".[geo]"
        import pyarrow.parquet as pq
        import shapely.geometry
        import shapely.wkb
        t = pq.read_table(path)
        cols = t.column_names
        for i in range(t.num_rows):
            g = shapely.wkb.loads(t["geometry"][i].as_py())
            if bbox and not (bbox[0] <= g.centroid.x <= bbox[2] and bbox[1] <= g.centroid.y <= bbox[3]):
                continue
            yield {"type": "Feature", "geometry": shapely.geometry.mapping(g),
                   "properties": {c: t[c][i].as_py() for c in cols if c != "geometry"}}
    else:
        raise ValueError(f"Unsupported file type {suf}; use .geojson, .geojsonl or .parquet")


def import_fields(conn: sqlite3.Connection, path: str, source: str, id_property: str | None = None,
                  bbox: tuple[float, float, float, float] | None = None, min_ha: float = 0.02, max_ha: float = 30.0) -> dict:
    """Satellite/registry field polygons -> field_candidates. Never touches plots (matching is an officer action)."""
    rep, skipped = Counter(), Counter()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for f in _features(Path(path), bbox):
        rep["read"] += 1
        s = geo.summarize(f.get("geometry") or {})
        if s is None:
            skipped["no polygon geometry"] += 1
            continue
        issues = geo.validate_ring(s["ring"])
        if issues:
            skipped[issues[0]] += 1
            continue
        if not (min_ha <= s["area_ha"] <= max_ha):
            skipped[f"area outside {min_ha}-{max_ha} ha"] += 1
            continue
        rec = str((f.get("properties") or {}).get(id_property) if id_property else
                  hashlib.sha1(s["geojson"].encode()).hexdigest()[:10])
        cur = conn.execute("INSERT OR IGNORE INTO field_candidates VALUES (?,?,?,?,?,?,?,?,?)",
                           (f"FC-{source}-{rec}", source, rec, s["geojson"], s["lat"], s["lon"], s["area_ha"], None, now))
        rep["imported" if cur.rowcount else "duplicate"] += 1
    conn.commit()
    return {"file": str(path), "source": source, **rep, "skipped": dict(skipped)}


DEFAULT_MAPPING = {"external_id": "id", "cluster_id": "cluster_id", "crop": "crop", "declared_area_ha": "area_ha",
                   "lat": "lat", "lon": "lon", "geojson": None, "village": "village", "tenure_type": "tenure",
                   "owner_name": "owner_name", "phone": "phone", "consent": "consent"}
TRUE = {"1", "true", "yes", "oui", "y", "granted"}


def import_plots_csv(conn: sqlite3.Connection, path: str, geometry_source: str, mapping: dict | None = None,
                     default_cluster: str | None = None, default_crop: str = "maize", pii_path: str | None = None) -> dict:
    """Farmer+plot list -> households + plots (pseudonymous) and, only with consent, identity in the PII database."""
    if geometry_source not in SOURCE_LEVEL:
        raise ValueError(f"geometry_source must be one of {sorted(SOURCE_LEVEL)}")
    m = {**DEFAULT_MAPPING, **(mapping or {})}
    salt = os.environ.get("EXTENSION_AGENT_PSEUDONYM_SALT", "dev-only-change-me")
    clusters = {r[0] for r in conn.execute("SELECT cluster_id FROM clusters")}
    rep, rejected = Counter(), Counter()
    ident = pii.connect(pii_path)
    seq = Counter()
    for row in csv.DictReader(open(path, newline="", encoding="utf-8-sig")):
        rep["read"] += 1
        get = lambda k: (row.get(m[k]) or "").strip() if m.get(k) else ""  # noqa: E731
        ext = get("external_id")
        cid = get("cluster_id") or default_cluster
        if not ext:
            rejected["missing external id"] += 1; continue
        if cid not in clusters:
            rejected[f"unknown cluster '{cid}'"] += 1; continue
        code = "FRM-" + hashlib.sha256((salt + ext).encode()).hexdigest()[:6].upper()
        if conn.execute("SELECT 1 FROM households WHERE farmer_code=?", (code,)).fetchone():
            rejected["duplicate external id"] += 1; continue
        summary = None
        if get("geojson"):
            summary = geo.summarize(json.loads(get("geojson")))
        elif get("lat") and get("lon"):
            try:
                lat, lon = float(get("lat")), float(get("lon"))
            except ValueError:
                rejected["non-numeric lat/lon"] += 1; continue
            lo, la, hi, ha = geo.BENIN_BBOX
            if not (lo <= lon <= hi and la <= lat <= ha):
                rejected["point outside Benin (lat/lon swapped?)"] += 1; continue
            summary = {"ring": None, "lat": lat, "lon": lon, "geojson": None, "area_ha": None}
        if summary and summary["ring"]:
            issues = geo.validate_ring(summary["ring"])
            if issues:
                rejected[f"invalid polygon: {issues[0]}"] += 1; continue
        seq[cid] += 1
        n = conn.execute("SELECT COUNT(*) FROM households WHERE cluster_id=?", (cid,)).fetchone()[0] + 1
        hid = f"HH-{cid.replace('-', '')}-{n:03d}"
        try:
            area = float(get("declared_area_ha")) if get("declared_area_ha") else None
        except ValueError:
            area = None
        conn.execute("INSERT INTO households (household_id, farmer_code, cluster_id, crop, area_ha, has_irrigation, planting_status) "
                     "VALUES (?,?,?,?,?,0,'not_planted')", (hid, code, cid, get("crop") or default_crop, area))
        cl = conn.execute("SELECT latitude, longitude, commune FROM clusters WHERE cluster_id=?", (cid,)).fetchone()
        has_loc = summary is not None
        conn.execute("INSERT INTO plots (plot_id, household_id, geometry_geojson, centroid_lat, centroid_lon, area_computed_ha, "
                     "geometry_source, verification_level, tenure_type, village, source_record_id, captured_on) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                     ("PL-" + hid.removeprefix("HH-"), hid, summary["geojson"] if has_loc else None,
                      summary["lat"] if has_loc else cl["latitude"], summary["lon"] if has_loc else cl["longitude"],
                      summary["area_ha"] if has_loc else None, geometry_source if has_loc else "village_only",
                      SOURCE_LEVEL[geometry_source] if has_loc else "declared", get("tenure_type") or "unknown",
                      get("village") or cl["commune"], ext, datetime.now(timezone.utc).date().isoformat()))
        c = geo.grid_cell(*(((summary["lat"], summary["lon"])) if has_loc else (cl["latitude"], cl["longitude"])))
        conn.execute("INSERT OR IGNORE INTO weather_cells VALUES (?,?,?,?)", (c["cell_id"], c["center_lat"], c["center_lon"], geo.GRID_STEP))
        consent = get("consent").lower() in TRUE
        if consent and (get("owner_name") or get("phone")):
            ident.execute("INSERT OR REPLACE INTO farmer_identity VALUES (?,?,?,?,?,?,?)",
                          (code, ext, get("owner_name"), get("phone"), "granted", datetime.now(timezone.utc).date().isoformat(), geometry_source))
            rep["identity_stored_with_consent"] += 1
        else:
            rep["identity_not_stored (no consent or no name)"] += 1
        rep["imported"] += 1
        rep["with_polygon" if (has_loc and summary["ring"]) else "with_point_only" if has_loc else "village_only"] += 1
    conn.commit(); ident.commit(); ident.close()
    return {"file": str(path), "geometry_source": geometry_source, **rep, "rejected": dict(rejected)}
