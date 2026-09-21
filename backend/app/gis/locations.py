"""Resolve shipment origin/destination from cities config + border gates DB."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import BorderGate
from app.gis.cities import list_cities
from app.gis.routing import fetch_road_route


def _norm(name: str) -> str:
    return " ".join((name or "").strip().lower().split())


def resolve_place(db: Session, place: str) -> dict[str, Any] | None:
    """Look up a place name against border gates (DB) then cities (config)."""
    key = _norm(place)
    if not key:
        return None

    gates = list(db.execute(select(BorderGate)).scalars())
    cities = list_cities()

    def gate_row(g: BorderGate) -> dict[str, Any]:
        return {
            "name": g.name,
            "latitude": float(g.latitude),
            "longitude": float(g.longitude),
            "kind": "gate",
            "region": g.location,
            "gate_status": g.status,
            "gate_id": g.id,
        }

    def city_row(c: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": c["name"],
            "latitude": float(c["latitude"]),
            "longitude": float(c["longitude"]),
            "kind": "city",
            "region": c.get("region"),
            "gate_status": None,
            "gate_id": None,
        }

    # 1) Exact gate name
    for g in gates:
        if g.latitude is None or g.longitude is None:
            continue
        if _norm(g.name) == key:
            return gate_row(g)

    # 2) Exact city name
    for c in cities:
        if _norm(c["name"]) == key:
            return city_row(c)

    # 3) Partial gate (longer names only, e.g. "Yangon Port")
    for g in gates:
        if g.latitude is None or g.longitude is None:
            continue
        gn = _norm(g.name)
        if len(gn) > len(key) and key in gn:
            return gate_row(g)

    # 4) Partial city
    for c in cities:
        cn = _norm(c["name"])
        if key in cn or cn in key:
            return city_row(c)
    return None


def list_route_locations(db: Session) -> list[dict[str, Any]]:
    """Unified dropdown source: cities + border gates (gates win on same name)."""
    by_name: dict[str, dict[str, Any]] = {}
    for c in list_cities():
        by_name[_norm(c["name"])] = {
            "name": c["name"],
            "latitude": c["latitude"],
            "longitude": c["longitude"],
            "kind": "city",
            "region": c.get("region"),
            "gate_status": None,
            "gate_id": None,
        }
    for g in db.execute(select(BorderGate).order_by(BorderGate.name)).scalars():
        if g.latitude is None or g.longitude is None:
            continue
        by_name[_norm(g.name)] = {
            "name": g.name,
            "latitude": float(g.latitude),
            "longitude": float(g.longitude),
            "kind": "gate",
            "region": g.location,
            "gate_status": g.status,
            "gate_id": g.id,
        }
    return sorted(by_name.values(), key=lambda x: x["name"].lower())


def route_preview(db: Session, origin: str, destination: str) -> dict[str, Any]:
    o = resolve_place(db, origin)
    d = resolve_place(db, destination)
    gates_on_route = []
    for place in (o, d):
        if place and place.get("kind") == "gate":
            gates_on_route.append(
                {
                    "name": place["name"],
                    "status": place.get("gate_status"),
                    "gate_id": place.get("gate_id"),
                }
            )
    warnings: list[str] = []
    for g in gates_on_route:
        st = (g.get("status") or "OPEN").upper()
        if st == "CLOSED":
            warnings.append(f"{g['name']} gate is CLOSED — consider delaying or alternate route")
        elif st == "WARNING":
            warnings.append(f"{g['name']} gate is WARNING — monitor closely")

    road = None
    route_line = None
    if o and d:
        road = fetch_road_route(
            o["latitude"], o["longitude"], d["latitude"], d["longitude"]
        )
        route_line = road["route_line"]
        if road.get("source") == "straight_line":
            warnings.append("Live road routing unavailable — showing straight corridor")

    return {
        "origin": o,
        "destination": d,
        "resolved": bool(o and d),
        "gates_on_route": gates_on_route,
        "warnings": warnings,
        "route_line": route_line,
        "distance_km": road.get("distance_km") if road else None,
        "duration_hours": road.get("duration_hours") if road else None,
        "route_source": road.get("source") if road else None,
    }
