"""Dependency-free geometry helpers (WGS84 lon/lat). Accurate enough for plot-scale areas and 5 km grids."""
from __future__ import annotations

import json
import math

BENIN_BBOX = (0.7, 6.1, 3.9, 12.5)  # lon_min, lat_min, lon_max, lat_max (generous)
GRID_STEP = 0.05                    # ~5.5 km, the native CHIRPS resolution


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(a))


def grid_cell(lat: float, lon: float, step: float = GRID_STEP) -> dict:
    i, j = math.floor(round(lat / step, 6)), math.floor(round(lon / step, 6))
    clat, clon = round((i + 0.5) * step, 4), round((j + 0.5) * step, 4)
    return {"cell_id": f"g{int(step * 1000):03d}_{clat:.3f}_{clon:.3f}", "center_lat": clat, "center_lon": clon}


def _proj(ring, lat0):
    kx = 111_320 * math.cos(math.radians(lat0))
    return [((lon - ring[0][0]) * kx, (lat - ring[0][1]) * 110_574) for lon, lat in ring]


def ring_area_ha(ring) -> float:
    xy = _proj(ring, ring[0][1])
    s = sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(xy, xy[1:] + xy[:1]))
    return abs(s) / 2 / 10_000


def ring_centroid(ring) -> tuple[float, float]:
    """(lat, lon) of the polygon centroid (planar, local projection)."""
    r = ring[:-1] if ring[0] == ring[-1] else ring
    xy = _proj(r, r[0][1])
    a = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(xy, xy[1:] + xy[:1]):
        c = x1 * y2 - x2 * y1
        a, cx, cy = a + c, cx + (x1 + x2) * c, cy + (y1 + y2) * c
    if abs(a) < 1e-9:
        return sum(p[1] for p in r) / len(r), sum(p[0] for p in r) / len(r)
    cx, cy = cx / (3 * a), cy / (3 * a)
    lon0, lat0 = r[0]
    return lat0 + cy / 110_574, lon0 + cx / (111_320 * math.cos(math.radians(lat0)))


def outer_ring(geometry: dict) -> list | None:
    """Largest outer ring of a GeoJSON Polygon/MultiPolygon, or None."""
    t, c = geometry.get("type"), geometry.get("coordinates")
    if t == "Polygon" and c:
        return c[0]
    if t == "MultiPolygon" and c:
        return max((p[0] for p in c if p), key=ring_area_ha, default=None)
    return None


def validate_ring(ring) -> list[str]:
    issues = []
    if not ring or len(ring) < 4:
        return ["fewer than 4 points"]
    if ring[0] != ring[-1]:
        issues.append("ring not closed")
    for lon, lat in ring:
        if not (math.isfinite(lon) and math.isfinite(lat)):
            return ["non-finite coordinate"]
    lo, la, hi, ha = BENIN_BBOX
    if not all(lo <= x <= hi and la <= y <= ha for x, y in ring):
        issues.append("outside Benin bounding box (lon/lat swapped?)")
    elif ring_area_ha(ring) < 0.005:
        issues.append("area below 0.005 ha")
    elif ring_area_ha(ring) > 500:
        issues.append("area above 500 ha (not a smallholder plot)")
    return issues


def square_polygon(lat: float, lon: float, area_ha: float, jitter: float = 0.0) -> dict:
    side = math.sqrt(area_ha * 10_000)
    dy = side / 2 / 110_574
    dx = side / 2 / (111_320 * math.cos(math.radians(lat)))
    ring = [[lon - dx, lat - dy], [lon + dx, lat - dy], [lon + dx + jitter * dx, lat + dy],
            [lon - dx, lat + dy + jitter * dy], [lon - dx, lat - dy]]
    return {"type": "Polygon", "coordinates": [[[round(x, 6), round(y, 6)] for x, y in ring]]}


def summarize(geometry: dict) -> dict | None:
    ring = outer_ring(geometry)
    if ring is None:
        return None
    lat, lon = ring_centroid(ring)
    return {"ring": ring, "area_ha": round(ring_area_ha(ring), 3), "lat": round(lat, 6), "lon": round(lon, 6),
            "geojson": json.dumps({"type": "Polygon", "coordinates": [ring]}, separators=(",", ":"))}
