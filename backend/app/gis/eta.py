"""Map distance + weather-adjusted delivery ETA (haversine → road factor → ETA)."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.gis.locations import list_route_locations, resolve_place
from app.gis.routing import fetch_road_route
from app.gis.spatial import haversine_km

ROAD_FACTOR = 1.35
BASE_SPEED_KMH = 42.0

_FILLER = re.compile(
    r"\b(delivery|deliver|eta|time|hours?|days?|risk|safe|route|road|trip|"
    r"shipment|how|long|take|from|ပို့ချိန်|ကြာ|ဘယ်လောက်|လား|နိုင်|လဲ)\b",
    re.I,
)
_DELIMS = re.compile(
    r"\s*[-–—→~/|]\s*|\s+to\s+|\s+မှ\s+|\s+ကနေ\s+|\s+သို့\s+",
    re.I,
)


def _clean(seg: str) -> str:
    s = _FILLER.sub(" ", seg or "")
    return " ".join(re.sub(r"[?？!！。．,]+", " ", s).split()).strip()


def find_places_in_text(db: Session, text: str) -> list[str]:
    """
    Dynamic place detection from cities + border gates (DB/config) — no alias file.
    Uses delimiter split + longest-name scan against the live gazetteer.
    """
    found: list[str] = []
    raw = text or ""

    # 1) Delimiter corridor: A-B / A→B / A to B
    for part in _DELIMS.split(raw):
        cleaned = _clean(part)
        if not cleaned:
            continue
        candidates = [cleaned]
        m = re.match(r"^([\w .'-]{2,40})", cleaned)
        if m:
            candidates.append(m.group(1).strip())
        m2 = re.match(r"^([\u1000-\u109F\uAA60-\uAA7F]{2,30})", cleaned)
        if m2:
            candidates.append(m2.group(1))
        for cand in candidates:
            hit = resolve_place(db, cand)
            if hit and hit["name"] not in found:
                found.append(hit["name"])
                break

    # 2) Longest-match scan of known English place names in the question
    places = list_route_locations(db)
    patterns = sorted(
        ((p["name"], p["name"].lower()) for p in places if p.get("name")),
        key=lambda x: len(x[1]),
        reverse=True,
    )
    lower = raw.lower()
    occupied = [False] * (len(lower) + 1)
    hits: list[tuple[int, str]] = []
    for name, key in patterns:
        start = 0
        while True:
            idx = lower.find(key, start)
            if idx < 0:
                break
            end = idx + len(key)
            if not any(occupied[i] for i in range(idx, end)):
                hits.append((idx, name))
                for i in range(idx, end):
                    occupied[i] = True
            start = idx + 1
    hits.sort(key=lambda x: x[0])
    for _, name in hits:
        if name not in found:
            found.append(name)

    return found


def resolve_map_corridor(
    db: Session,
    question: str,
    shipment_origin: str | None = None,
    shipment_dest: str | None = None,
) -> tuple[str | None, str | None]:
    """Prefer places found in the question; else bound shipment endpoints."""
    q_places = find_places_in_text(db, question)
    if len(q_places) >= 2:
        return q_places[0], q_places[1]
    if len(q_places) == 1 and shipment_origin and shipment_dest:
        only = q_places[0].lower()
        if only in shipment_origin.lower() or only in shipment_dest.lower():
            return shipment_origin, shipment_dest
        # Single named place ≠ shipment pair — still need two ends for map
        return shipment_origin, shipment_dest
    if shipment_origin and shipment_dest:
        return shipment_origin, shipment_dest
    if len(q_places) >= 2:
        return q_places[0], q_places[1]
    return None, None


def estimate_route_metrics(
    db: Session,
    origin: str | None,
    destination: str | None,
    weather: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Straight-line haversine × road factor → weather-adjusted ETA."""
    if not origin or not destination:
        return None
    o = resolve_place(db, origin)
    d = resolve_place(db, destination)
    if not o or not d:
        return None
    if o["name"] == d["name"]:
        return None

    straight_km = haversine_km(o["latitude"], o["longitude"], d["latitude"], d["longitude"])
    road = fetch_road_route(o["latitude"], o["longitude"], d["latitude"], d["longitude"])
    road_km = float(road.get("distance_km") or round(straight_km * ROAD_FACTOR, 1))

    speed = BASE_SPEED_KMH
    weather_note = "clear driving assumptions"
    if weather:
        rain = float(weather.get("rainfall") or 0)
        flood = str(weather.get("flood_risk") or "").lower()
        cond = str(weather.get("condition") or "")
        if weather.get("storm") or flood == "high" or rain >= 30:
            speed *= 0.55
            weather_note = f"slowed for severe weather (storm/flood_risk={flood}, rain={rain}mm)"
        elif flood == "medium" or rain >= 5 or "rain" in cond.lower():
            speed *= 0.75
            weather_note = f"slowed for rain (condition={cond}, rain={rain}mm, flood_risk={flood})"
        else:
            weather_note = f"near-normal pace (condition={cond}, rain={rain}mm)"

    # Prefer OSRM duration when available, then apply weather speed factor vs base
    if road.get("duration_hours") and road.get("source") == "osrm":
        base_hours = float(road["duration_hours"])
        weather_factor = speed / BASE_SPEED_KMH
        hours = base_hours / max(weather_factor, 0.35)
    else:
        hours = road_km / max(speed, 8.0)
    buffer_h = 0.5 if road_km < 150 else 1.0 if road_km < 400 else 1.5
    hours_low = max(1.0, hours)
    hours_high = hours + buffer_h

    def _fmt(h: float) -> str:
        if h < 24:
            return f"{h:.1f} hours"
        return f"{h / 24.0:.1f} days ({h:.0f} h)"

    return {
        "origin": o["name"],
        "destination": d["name"],
        "origin_lat": o["latitude"],
        "origin_lon": o["longitude"],
        "dest_lat": d["latitude"],
        "dest_lon": d["longitude"],
        "straight_km": round(straight_km, 1),
        "road_km": round(road_km, 1),
        "assumed_speed_kmh": round(speed, 1),
        "eta_hours_low": round(hours_low, 1),
        "eta_hours_high": round(hours_high, 1),
        "eta_text": f"about {_fmt(hours_low)}–{_fmt(hours_high)}",
        "weather_note": weather_note,
        "route_line": road["route_line"],
        "route_source": road.get("source"),
        "source": f"map_{road.get('source', 'haversine')}+weather",
    }
