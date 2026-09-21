"""Road-following route geometry via OSRM (fallback: straight line)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.gis.spatial import haversine_km

logger = logging.getLogger(__name__)

# In-memory cache: (round lat/lon) → route payload
_ROUTE_CACHE: dict[tuple[float, float, float, float], dict[str, Any]] = {}


def _straight_line(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> dict[str, Any]:
    km = haversine_km(lat1, lon1, lat2, lon2)
    return {
        "route_line": [[lat1, lon1], [lat2, lon2]],
        "distance_km": round(km * 1.35, 1),
        "duration_hours": None,
        "source": "straight_line",
    }


def fetch_road_route(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> dict[str, Any]:
    """
    Return Leaflet-friendly route_line [[lat, lon], ...] following real roads.
    Uses public OSRM by default; falls back to straight line if unreachable.
    """
    key = (round(lat1, 4), round(lon1, 4), round(lat2, 4), round(lon2, 4))
    hit = _ROUTE_CACHE.get(key)
    if hit is not None:
        return hit

    settings = get_settings()
    base = (getattr(settings, "osrm_url", None) or "https://router.project-osrm.org").rstrip(
        "/"
    )
    url = f"{base}/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"
    params = {"overview": "simplified", "geometries": "geojson"}

    try:
        with httpx.Client(timeout=12.0) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        routes = data.get("routes") or []
        if not routes:
            raise ValueError(data.get("message") or "no routes")
        route = routes[0]
        coords = (route.get("geometry") or {}).get("coordinates") or []
        # GeoJSON is [lon, lat] → Leaflet [lat, lon]
        line = [[float(lat), float(lon)] for lon, lat in coords]
        if len(line) < 2:
            raise ValueError("empty geometry")
        payload = {
            "route_line": line,
            "distance_km": round(float(route.get("distance") or 0) / 1000.0, 1),
            "duration_hours": round(float(route.get("duration") or 0) / 3600.0, 2),
            "source": "osrm",
        }
        _ROUTE_CACHE[key] = payload
        return payload
    except Exception as exc:
        logger.warning("OSRM routing failed (%s); using straight line", exc)
        payload = _straight_line(lat1, lon1, lat2, lon2)
        _ROUTE_CACHE[key] = payload
        return payload
