"""PostGIS / spatial helpers."""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Iterable

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.database.models import VehiclePosition


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


def point_wkt(lon: float, lat: float) -> str:
    return f"SRID=4326;POINT({lon} {lat})"


def latest_vehicle_position(db: Session, vehicle_id: int) -> VehiclePosition | None:
    stmt = (
        select(VehiclePosition)
        .where(VehiclePosition.vehicle_id == vehicle_id)
        .order_by(VehiclePosition.timestamp.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def positions_within_radius_km(
    db: Session,
    latitude: float,
    longitude: float,
    radius_km: float = 50.0,
) -> list[VehiclePosition]:
    """Use PostGIS geography distance when available; else Python fallback."""
    try:
        sql = text(
            """
            SELECT id FROM vehicle_positions
            WHERE geom IS NOT NULL
              AND ST_DWithin(
                    geom,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                    :meters
              )
            ORDER BY timestamp DESC
            LIMIT 50
            """
        )
        ids = [
            row[0]
            for row in db.execute(
                sql, {"lat": latitude, "lon": longitude, "meters": radius_km * 1000}
            )
        ]
        if not ids:
            return []
        stmt = select(VehiclePosition).where(VehiclePosition.id.in_(ids))
        return list(db.execute(stmt).scalars())
    except Exception:
        positions = list(db.execute(select(VehiclePosition)).scalars())
        return [
            p
            for p in positions
            if haversine_km(latitude, longitude, p.latitude, p.longitude) <= radius_km
        ]


MYANMAR_CORRIDOR_HINTS = {
    "myawaddy": (16.6897, 98.5089),
    "muse": (23.9780, 97.9040),
    "yangon": (16.8409, 96.1735),
    "mandalay": (21.9588, 96.0891),
    "tamu": (24.2153, 94.3100),
}


def infer_corridor_coords(place: str) -> tuple[float, float] | None:
    """Resolve coords from static city list (never call live weather here)."""
    from app.gis.cities import MYANMAR_CITIES

    key = (place or "").strip().lower()
    if not key:
        return None
    for c in MYANMAR_CITIES:
        name = str(c["name"]).lower()
        if name == key or name in key or key in name:
            return float(c["lat"]), float(c["lon"])
    for name, coords in MYANMAR_CORRIDOR_HINTS.items():
        if name in key:
            return coords
    return None


def route_risk_zones(
    origin: str, destination: str
) -> list[dict]:
    """Prototype risk zone polygons as circle centers for the map."""
    zones = []
    seen: set[tuple[float, float]] = set()
    for label in (origin, destination, "Myawaddy"):
        coords = infer_corridor_coords(label)
        if not coords:
            continue
        key = (round(coords[0], 4), round(coords[1], 4))
        if key in seen:
            continue
        seen.add(key)
        zones.append(
            {
                "name": label,
                "latitude": coords[0],
                "longitude": coords[1],
                "radius_km": 35,
                "level": "elevated" if "myawaddy" in label.lower() else "watch",
            }
        )
    return zones


def _jitter_points(
    lat: float, lon: float, intensity: float, *, n: int = 8, spread_deg: float = 0.18
) -> list[dict]:
    """Spread heat samples around a center so leaflet.heat renders a blob."""
    pts = [{"latitude": lat, "longitude": lon, "intensity": intensity, "source": "center"}]
    if n <= 1:
        return pts
    for i in range(n - 1):
        angle = (2 * 3.14159265 * i) / (n - 1)
        r = spread_deg * (0.35 + 0.65 * ((i % 3) / 2))
        pts.append(
            {
                "latitude": lat + r * cos(angle),
                "longitude": lon + r * sin(angle),
                "intensity": max(0.05, intensity * (0.55 + 0.35 * ((i % 2)))),
                "source": "ring",
            }
        )
    return pts


def build_risk_heatmap(
    *,
    zones: list[dict],
    gates: list[dict],
    vehicles: list[dict],
    shipments: list[dict] | None = None,
) -> list[dict]:
    """Build leaflet.heat points [lat, lon intensity] from live risk signals."""
    points: list[dict] = []

    for z in zones:
        base = 0.75 if (z.get("level") or "") == "elevated" else 0.4
        points.extend(
            _jitter_points(float(z["latitude"]), float(z["longitude"]), base, n=10, spread_deg=0.22)
        )

    for g in gates:
        lat, lon = g.get("latitude"), g.get("longitude")
        if lat is None or lon is None:
            continue
        st = (g.get("status") or "OPEN").upper()
        if st == "CLOSED":
            intensity = 1.0
        elif st == "WARNING":
            intensity = 0.7
        else:
            continue
        points.extend(_jitter_points(float(lat), float(lon), intensity, n=12, spread_deg=0.16))

    for v in vehicles:
        level = (v.get("risk_level") or "").upper()
        if level == "HIGH":
            intensity = 0.9
        elif level == "MEDIUM":
            intensity = 0.55
        else:
            # still add mild heat from weather flood risk near vehicle
            wx = v.get("weather") or {}
            fr = str(wx.get("flood_risk") or "").lower()
            rain = float(wx.get("rainfall") or 0)
            if fr == "high" or rain >= 20:
                intensity = 0.8
            elif fr == "medium" or rain >= 5:
                intensity = 0.45
            else:
                continue
        points.extend(
            _jitter_points(float(v["latitude"]), float(v["longitude"]), intensity, n=6, spread_deg=0.08)
        )

    # Corridor midpoints for active shipments with elevated risk
    for s in shipments or []:
        score = s.get("latest_risk_score")
        level = (s.get("latest_risk_level") or "").upper()
        o_lat, o_lon = s.get("origin_lat"), s.get("origin_lon")
        d_lat, d_lon = s.get("dest_lat"), s.get("dest_lon")
        if o_lat is None or d_lat is None:
            continue
        if level not in {"HIGH", "MEDIUM"} and not (isinstance(score, (int, float)) and score >= 0.4):
            continue
        intensity = 0.85 if level == "HIGH" or (score or 0) >= 0.7 else 0.5
        # sample along route
        for t in (0.25, 0.5, 0.75):
            lat = float(o_lat) + (float(d_lat) - float(o_lat)) * t
            lon = float(o_lon) + (float(d_lon) - float(o_lon)) * t
            points.extend(_jitter_points(lat, lon, intensity, n=5, spread_deg=0.12))

    # Clamp / round for payload size
    out = []
    for p in points:
        out.append(
            {
                "latitude": round(float(p["latitude"]), 5),
                "longitude": round(float(p["longitude"]), 5),
                "intensity": round(min(1.0, max(0.05, float(p["intensity"]))), 3),
            }
        )
    return out
