"""Shared plot-location logic: how precisely do we know where a plot is, and which weather cell covers it."""
from __future__ import annotations

import sqlite3

from .. import geo

CONFIDENCE = {
    "cadastral": "high", "officer_surveyed": "high", "officer_matched": "medium",
    "satellite_candidate": "low", "declared": "very_low", "synthetic_test": "low",
}
NOTE = {
    "high": "Plot boundary measured or registered; weather is still a grid estimate.",
    "medium": "Satellite-detected field confirmed by an officer; boundary approximate.",
    "low": "Satellite-detected field NOT confirmed by an officer; may not be this farmer's plot.",
    "very_low": "No plot geometry: located only to the village/cluster centroid.",
}


def plot_for(conn: sqlite3.Connection, plot_id: str):
    return conn.execute("SELECT p.*, h.cluster_id, h.area_ha AS declared_ha FROM plots p "
                        "JOIN households h USING (household_id) WHERE p.plot_id=?", (plot_id,)).fetchone()


def describe(row) -> dict:
    """Location facts for one plot (no owner information)."""
    has_geom = row["geometry_geojson"] is not None
    conf = CONFIDENCE.get(row["verification_level"], "very_low")
    declared, computed = row["declared_ha"], row["area_computed_ha"]
    if has_geom and declared:
        ratio = computed / declared
        area_check = "consistent" if 0.65 <= ratio <= 1.35 else f"mismatch (mapped {computed} ha vs declared {declared} ha)"
    else:
        area_check = "not_checkable"
    cell = geo.grid_cell(row["centroid_lat"], row["centroid_lon"]) if row["centroid_lat"] is not None else None
    return {
        "plot_id": row["plot_id"], "geometry_source": row["geometry_source"],
        "verification_level": row["verification_level"], "location_confidence": conf,
        "location_note": NOTE[conf],
        "location_precision": "polygon" if has_geom else "village_centroid",
        "centroid": {"lat": row["centroid_lat"], "lon": row["centroid_lon"]},
        "area_mapped_ha": computed, "area_declared_ha": row["declared_ha"], "area_check": area_check,
        "tenure_type": row["tenure_type"], "village": row["village"],
        "weather_cell_id": cell["cell_id"] if cell else None,
    }
