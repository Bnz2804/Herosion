"""Rank satellite-detected fields near a plot and let an officer confirm one (never automatic)."""
from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone

from . import geo

PROTECTED = {"cadastral", "officer_surveyed"}  # never overwritten by a satellite match


def candidates_for(conn: sqlite3.Connection, plot_id: str, radius_km: float = 2.0, limit: int = 8) -> dict | None:
    p = conn.execute("SELECT p.*, h.area_ha AS declared_ha FROM plots p JOIN households h USING (household_id) "
                     "WHERE plot_id=?", (plot_id,)).fetchone()
    if p is None:
        return None
    lat, lon = p["centroid_lat"], p["centroid_lon"]
    dlat = radius_km / 110.574
    dlon = radius_km / (111.32 * math.cos(math.radians(lat)))
    rows = conn.execute("SELECT * FROM field_candidates WHERE centroid_lat BETWEEN ? AND ? AND centroid_lon BETWEEN ? AND ?",
                        (lat - dlat, lat + dlat, lon - dlon, lon + dlon)).fetchall()
    taken = {r["source_record_id"] for r in conn.execute(
        "SELECT source_record_id FROM plots WHERE source_record_id IS NOT NULL AND plot_id != ?", (plot_id,))}
    out = []
    for r in rows:
        dist = geo.haversine_km(lat, lon, r["centroid_lat"], r["centroid_lon"])
        if dist > radius_km:
            continue
        declared = p["declared_ha"]
        ratio = r["area_ha"] / declared if declared else None
        area_score = 0.5 if ratio is None else max(0.0, 1 - abs(math.log(ratio)) / math.log(3))
        score = round(0.55 * max(0.0, 1 - dist / radius_km) + 0.45 * area_score, 3)
        reasons = [f"{dist * 1000:.0f} m from the {'plot' if p['geometry_geojson'] else 'village centroid'}",
                   f"{r['area_ha']} ha" + (f" vs declared {declared} ha" if declared else " (declared area unknown)")]
        out.append({"candidateId": r["candidate_id"], "source": r["source"], "areaHa": r["area_ha"],
                    "distanceM": round(dist * 1000), "score": score, "reasons": reasons,
                    "alreadyMatched": r["candidate_id"] in taken,
                    "geometry": json.loads(r["geometry_geojson"])})
    out.sort(key=lambda c: -c["score"])
    return {"plotId": plot_id, "verificationLevel": p["verification_level"], "declaredAreaHa": p["declared_ha"],
            "origin": {"lat": lat, "lon": lon, "hasPolygon": p["geometry_geojson"] is not None},
            "candidates": out[:limit], "radiusKm": radius_km,
            "note": "Suggestions only. A satellite field is not a legal parcel; an officer must confirm it with the farmer."}


class MatchError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def confirm_match(conn: sqlite3.Connection, plot_id: str, candidate_id: str, officer: str) -> dict:
    officer = officer.strip()
    if len(officer) < 2:
        raise MatchError(400, "Enter the confirming officer's full name")
    p = conn.execute("SELECT * FROM plots WHERE plot_id=?", (plot_id,)).fetchone()
    c = conn.execute("SELECT * FROM field_candidates WHERE candidate_id=?", (candidate_id,)).fetchone()
    if p is None or c is None:
        raise MatchError(404, "Plot or field candidate not found")
    if p["verification_level"] in PROTECTED:
        raise MatchError(409, f"Plot is already {p['verification_level']}; a satellite match cannot replace it")
    other = conn.execute("SELECT plot_id FROM plots WHERE source_record_id=? AND plot_id!=?", (candidate_id, plot_id)).fetchone()
    if other:
        raise MatchError(409, f"Field {candidate_id} is already matched to {other['plot_id']}")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with conn:
        conn.execute("INSERT INTO plot_match_log (plot_id, candidate_id, officer, ts_utc, previous_source, previous_verification) "
                     "VALUES (?,?,?,?,?,?)", (plot_id, candidate_id, officer, now, p["geometry_source"], p["verification_level"]))
        conn.execute("UPDATE plots SET geometry_geojson=?, centroid_lat=?, centroid_lon=?, area_computed_ha=?, "
                     "geometry_source='satellite_field', verification_level='officer_matched', source_record_id=?, "
                     "matched_by=?, matched_at=?, captured_on=? WHERE plot_id=?",
                     (c["geometry_geojson"], c["centroid_lat"], c["centroid_lon"], c["area_ha"], candidate_id,
                      officer, now, now[:10], plot_id))
        cell = geo.grid_cell(c["centroid_lat"], c["centroid_lon"])
        conn.execute("INSERT OR IGNORE INTO weather_cells VALUES (?,?,?,?)",
                     (cell["cell_id"], cell["center_lat"], cell["center_lon"], geo.GRID_STEP))
    return {"plotId": plot_id, "candidateId": candidate_id, "verificationLevel": "officer_matched",
            "previousVerification": p["verification_level"], "weatherCellId": cell["cell_id"], "matchedBy": officer}
