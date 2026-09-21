"""Core logistics + driver action routes."""

from __future__ import annotations

import re
import random
import string
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from geoalchemy2.elements import WKTElement
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
import httpx

from app.api.schemas import (
    AiQueryIn,
    AiQueryOut,
    LocationOut,
    OsintIngestIn,
    ShipmentCreate,
    ShipmentOut,
    VehicleOut,
)
from app.core.config import get_settings
from app.core.security import (
    ROLE_ADMIN,
    ROLE_DRIVER,
    ROLE_TRADER,
    get_current_user,
    require_roles,
)
from app.database.models import (
    Alert,
    BorderGate,
    Driver,
    LogisticsRiskPrediction,
    Shipment,
    ShipmentEvent,
    User,
    Vehicle,
    VehiclePosition,
)
from app.database.postgres import get_db
from app.gis.cities import list_cities, list_map_cities
from app.gis.locations import list_route_locations, resolve_place, route_preview
from app.gis.spatial import build_risk_heatmap, latest_vehicle_position, route_risk_zones
from app.intelligence.agents.logistics_agent import LogisticsAgent
from app.osint.crawler import ingest_texts
from app.weather.weather_client import get_weather_client

router = APIRouter()

LIFECYCLE = [
    "CREATED",
    "PICKED_UP",
    "IN_TRANSIT",
    "CHECKPOINT",
    "CUSTOMS",
    "DELIVERED",
]

DRIVER_ACTIONS = {
    "start_trip": ("IN_TRANSIT", "Start Trip", "PICKED_UP"),
    "arrived_checkpoint": ("CHECKPOINT", "Arrived Checkpoint", "CHECKPOINT"),
    "customs_completed": ("CUSTOMS", "Customs Completed", "CUSTOMS"),
    "delivered": ("DELIVERED", "Delivered", "DELIVERED"),
    "report_problem": ("DELAYED", "Report Problem", "DELAYED"),
    "upload_document": (None, "Upload Document", "DOCUMENT"),
    "update_location": (None, "GPS update", "GPS"),
}

# Side-effect actions that do not advance (or may soft-set DELAYED) the lifecycle
_ALWAYS_ALLOWED_ACTIONS = frozenset({"update_location", "upload_document", "report_problem"})

# Status-changing trip actions → required current lifecycle anchor(s)
_ACTION_REQUIRED_STATUS: dict[str, frozenset[str]] = {
    "start_trip": frozenset({"CREATED"}),
    "arrived_checkpoint": frozenset({"IN_TRANSIT"}),
    "customs_completed": frozenset({"CHECKPOINT"}),
    "delivered": frozenset({"CUSTOMS"}),
}


def _normalize_lifecycle_status(status: str | None) -> str:
    u = (status or "CREATED").upper()
    if u in {"LOADING", "CREATED"}:
        return "CREATED"
    if u == "PICKED_UP":
        return "IN_TRANSIT"
    return u


def _lifecycle_anchor(db: Session, s: Shipment) -> str:
    """Current place in the trip graph (DELAYED resumes from last progressed step)."""
    status = _normalize_lifecycle_status(s.status)
    if status != "DELAYED":
        return status
    events = list(
        db.execute(
            select(ShipmentEvent)
            .where(ShipmentEvent.shipment_id == s.id)
            .order_by(ShipmentEvent.timestamp.asc())
        ).scalars()
    )
    types = {((e.event_type or "").upper()) for e in events}
    if "DELIVERED" in types:
        return "DELIVERED"
    if "CUSTOMS" in types:
        return "CUSTOMS"
    if "CHECKPOINT" in types:
        return "CHECKPOINT"
    if "PICKED_UP" in types or "IN_TRANSIT" in types or "GPS" in types:
        return "IN_TRANSIT"
    return "CREATED"


def _assert_driver_transition(db: Session, s: Shipment, action: str) -> None:
    """Reject lifecycle skips e.g. CREATED → delivered (HTTP 409)."""
    if action in _ALWAYS_ALLOWED_ACTIONS:
        if action == "report_problem" and _normalize_lifecycle_status(s.status) == "DELIVERED":
            raise HTTPException(409, "Cannot report problem on a delivered shipment")
        return
    required = _ACTION_REQUIRED_STATUS.get(action)
    if required is None:
        return
    anchor = _lifecycle_anchor(db, s)
    if anchor == "DELIVERED":
        raise HTTPException(409, "Shipment already delivered — no further trip actions")
    if anchor not in required:
        need = ", ".join(sorted(required))
        raise HTTPException(
            409,
            f"Cannot '{action}' from status {s.status or 'CREATED'} "
            f"(lifecycle at {anchor}; required: {need})",
        )


def _gen_tracking() -> str:
    return "SH" + "".join(random.choices(string.digits, k=3))


def _shipment_out(db: Session, s: Shipment) -> ShipmentOut:
    pred = db.execute(
        select(LogisticsRiskPrediction)
        .where(LogisticsRiskPrediction.shipment_id == s.id)
        .order_by(LogisticsRiskPrediction.timestamp.desc())
        .limit(1)
    ).scalar_one_or_none()
    return ShipmentOut(
        id=s.id,
        tracking_number=s.tracking_number,
        vehicle_id=s.vehicle_id,
        trader_id=getattr(s, "trader_id", None),
        driver_id=getattr(s, "driver_id", None),
        origin=s.origin,
        destination=s.destination,
        cargo_type=s.cargo_type,
        weight=s.weight,
        status=s.status,
        origin_lat=s.origin_lat,
        origin_lon=s.origin_lon,
        dest_lat=s.dest_lat,
        dest_lon=s.dest_lon,
        latest_risk_level=pred.risk_level if pred else None,
        latest_risk_score=pred.risk_score if pred else None,
    )


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/shipments", response_model=ShipmentOut)
def create_shipment(
    body: ShipmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(ROLE_ADMIN, ROLE_TRADER)),
):
    tracking = body.tracking_number or _gen_tracking()
    existing = db.execute(
        select(Shipment).where(Shipment.tracking_number == tracking)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(400, f"Tracking {tracking} already exists")

    origin_place = resolve_place(db, body.origin)
    dest_place = resolve_place(db, body.destination)
    if not origin_place:
        raise HTTPException(400, f"Unknown origin '{body.origin}' — pick a city or border gate")
    if not dest_place:
        raise HTTPException(400, f"Unknown destination '{body.destination}' — pick a city or border gate")
    if origin_place["name"] == dest_place["name"]:
        raise HTTPException(400, "Origin and destination must differ")

    trader_id = user.id if user.role == ROLE_TRADER else body.trader_id or user.id
    driver_id = body.driver_id
    if driver_id is None:
        # Demo default: assign first DRIVER account so Field Console sees new cargo
        default_driver = db.execute(
            select(User).where(User.role == ROLE_DRIVER).order_by(User.id.asc()).limit(1)
        ).scalar_one_or_none()
        if default_driver:
            driver_id = default_driver.id
    s = Shipment(
        tracking_number=tracking,
        vehicle_id=body.vehicle_id,
        trader_id=trader_id,
        driver_id=driver_id,
        origin=origin_place["name"],
        destination=dest_place["name"],
        cargo_type=body.cargo_type,
        weight=body.weight,
        status=body.status or "CREATED",
        origin_lat=origin_place["latitude"],
        origin_lon=origin_place["longitude"],
        dest_lat=dest_place["latitude"],
        dest_lon=dest_place["longitude"],
    )
    db.add(s)
    db.flush()
    gate_note = ""
    for place in (origin_place, dest_place):
        if place.get("kind") == "gate" and place.get("gate_status"):
            gate_note += f" · {place['name']}={place['gate_status']}"
    db.add(
        ShipmentEvent(
            shipment_id=s.id,
            event_type="CREATED",
            description=f"Shipment request created{gate_note}",
            location=s.origin,
            latitude=s.origin_lat,
            longitude=s.origin_lon,
            severity="info",
        )
    )
    # Warn trader if destination/origin gate is not OPEN
    for place in (origin_place, dest_place):
        st = (place.get("gate_status") or "").upper()
        if place.get("kind") == "gate" and st in {"CLOSED", "WARNING"}:
            db.add(
                Alert(
                    shipment_id=s.id,
                    severity="HIGH" if st == "CLOSED" else "MEDIUM",
                    message=(
                        f"Route touches {place['name']} gate ({st}). "
                        f"Shipment {tracking} ({s.origin} → {s.destination})."
                    ),
                )
            )
    db.commit()
    db.refresh(s)
    return _shipment_out(db, s)


@router.get("/shipments", response_model=list[ShipmentOut])
def list_shipments(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Shipment).order_by(Shipment.id.desc())
    if user.role == ROLE_TRADER:
        stmt = stmt.where(Shipment.trader_id == user.id)
    elif user.role == ROLE_DRIVER:
        # Assigned to this driver, or still unassigned (claimable in demo)
        stmt = stmt.where(
            (Shipment.driver_id == user.id) | (Shipment.driver_id.is_(None))
        )
    # ADMIN sees all
    rows = list(db.execute(stmt).scalars())
    return [_shipment_out(db, s) for s in rows]


def _assert_can_view_shipment(user: User, s: Shipment) -> None:
    """RBAC: ADMIN sees everything; TRADER only their own shipments;
    DRIVER only shipments assigned to them (or unassigned, for demo claiming)."""
    if user.role == ROLE_ADMIN:
        return
    if user.role == ROLE_TRADER and s.trader_id == user.id:
        return
    if user.role == ROLE_DRIVER and s.driver_id in (None, user.id):
        return
    raise HTTPException(403, "Not authorized to view this shipment")


@router.get("/shipments/{shipment_id}", response_model=ShipmentOut)
def get_shipment(
    shipment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    s = db.get(Shipment, shipment_id)
    if not s:
        raise HTTPException(404, "Shipment not found")
    _assert_can_view_shipment(user, s)
    return _shipment_out(db, s)


@router.get("/shipments/{shipment_id}/timeline")
def shipment_timeline(
    shipment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    s = db.get(Shipment, shipment_id)
    if not s:
        raise HTTPException(404, "Shipment not found")
    _assert_can_view_shipment(user, s)
    events = list(
        db.execute(
            select(ShipmentEvent)
            .where(ShipmentEvent.shipment_id == s.id)
            .order_by(ShipmentEvent.timestamp.asc())
        ).scalars()
    )
    done = {e.event_type.upper() for e in events}
    # Map legacy / alias event names into lifecycle steps
    if "DEPARTED" in done or "PICKED_UP" in done:
        done.add("PICKED_UP")
        done.add("IN_TRANSIT")
    if "CHECKPOINT" in done:
        done.update({"PICKED_UP", "IN_TRANSIT", "CHECKPOINT"})
    status_u = (s.status or "").upper()
    if status_u == "DELAYED":
        # keep last known progress; mark DELAYED via events only
        status_u = next(
            (st for st in reversed(LIFECYCLE) if st in done),
            "IN_TRANSIT",
        )
    try:
        current_idx = LIFECYCLE.index(status_u)
    except ValueError:
        current_idx = 0
        for i, step in enumerate(LIFECYCLE):
            if step in done:
                current_idx = i
    steps = []
    for i, step in enumerate(LIFECYCLE):
        if i < current_idx or step in done and i != current_idx:
            state = "done"
        elif i == current_idx:
            state = "current"
        else:
            state = "todo"
        # ensure earlier steps are done when later status reached
        if i < current_idx:
            state = "done"
        steps.append({"step": step, "state": state})
    return {
        "shipment_id": s.id,
        "tracking_number": s.tracking_number,
        "status": s.status,
        "steps": steps,
        "events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "description": e.description,
                "location": e.location,
                "latitude": e.latitude,
                "longitude": e.longitude,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "document_name": getattr(e, "document_name", None),
                "content_type": getattr(e, "content_type", None),
                "file_size": getattr(e, "file_size", None),
                "document_url": (
                    f"/api/shipments/{s.id}/documents/{e.id}/file"
                    if getattr(e, "document_path", None)
                    else None
                ),
            }
            for e in events
        ],
    }


@router.get("/shipments/{shipment_id}/risk")
def shipment_risk(
    shipment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    s = db.get(Shipment, shipment_id)
    if not s:
        raise HTTPException(404, "Shipment not found")
    _assert_can_view_shipment(user, s)
    agent = LogisticsAgent(db)
    return agent.assess(
        question=f"Check risk for shipment {s.tracking_number}",
        shipment_id=s.id,
    )


class DriverActionIn(BaseModel):
    action: str
    latitude: float | None = None
    longitude: float | None = None
    note: str | None = None
    document_name: str | None = None


@router.post("/shipments/{shipment_id}/driver-action")
def driver_action(
    shipment_id: int,
    body: DriverActionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(ROLE_DRIVER, ROLE_ADMIN)),
):
    s = db.get(Shipment, shipment_id)
    if not s:
        raise HTTPException(404, "Shipment not found")
    if user.role == ROLE_DRIVER and s.driver_id not in (None, user.id):
        # allow if assigned or unassigned for demo
        if s.driver_id and s.driver_id != user.id:
            raise HTTPException(403, "Not your shipment")
    if body.action not in DRIVER_ACTIONS:
        raise HTTPException(400, f"Unknown action {body.action}")
    if body.action == "update_location" and (body.latitude is None or body.longitude is None):
        raise HTTPException(400, "latitude and longitude required for GPS update")
    _assert_driver_transition(db, s, body.action)
    new_status, label, event_type = DRIVER_ACTIONS[body.action]
    if new_status:
        s.status = new_status
    if s.driver_id is None and user.role == ROLE_DRIVER:
        s.driver_id = user.id
    desc = body.note or label
    if body.document_name:
        desc = f"{label}: {body.document_name}"
    if body.action == "update_location" and body.latitude is not None and body.longitude is not None:
        desc = f"GPS update ({body.latitude:.5f}, {body.longitude:.5f})"
    db.add(
        ShipmentEvent(
            shipment_id=s.id,
            event_type=event_type,
            description=desc,
            location=s.destination if new_status == "DELIVERED" else s.origin,
            latitude=body.latitude,
            longitude=body.longitude,
            severity="warning" if body.action == "report_problem" else "info",
        )
    )
    if body.latitude is not None and body.longitude is not None:
        vehicle_id = s.vehicle_id
        if vehicle_id is None:
            driver_row = db.execute(
                select(Driver).where(Driver.user_id == user.id)
            ).scalar_one_or_none()
            if driver_row:
                veh = db.execute(
                    select(Vehicle).where(Vehicle.driver_id == driver_row.id).limit(1)
                ).scalar_one_or_none()
                if veh:
                    vehicle_id = veh.id
                    s.vehicle_id = veh.id
        if vehicle_id:
            db.add(
                VehiclePosition(
                    vehicle_id=vehicle_id,
                    latitude=body.latitude,
                    longitude=body.longitude,
                    speed=0,
                    timestamp=datetime.now(timezone.utc),
                    geom=WKTElement(f"POINT({body.longitude} {body.latitude})", srid=4326),
                )
            )
    if body.action == "report_problem":
        db.add(
            Alert(
                shipment_id=s.id,
                severity="HIGH",
                message=f"Driver reported problem on {s.tracking_number}: {desc}",
            )
        )
    db.commit()
    db.refresh(s)
    return {"ok": True, "shipment": _shipment_out(db, s)}


def _safe_filename(name: str) -> str:
    base = Path(name or "document.bin").name
    cleaned = re.sub(r"[^\w.\-()+ ]+", "_", base).strip("._ ") or "document.bin"
    return cleaned[:180]


def _upload_root() -> Path:
    settings = get_settings()
    root = Path(settings.upload_dir)
    if not root.is_absolute():
        # resolve relative to backend package parent (…/backend/uploads)
        root = Path(__file__).resolve().parents[2] / root
    root.mkdir(parents=True, exist_ok=True)
    return root


@router.post("/shipments/{shipment_id}/documents")
async def upload_shipment_document(
    shipment_id: int,
    file: UploadFile = File(...),
    latitude: float | None = Form(default=None),
    longitude: float | None = Form(default=None),
    note: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(ROLE_DRIVER, ROLE_ADMIN)),
):
    """Accept a real file from driver file-picker and attach as DOCUMENT event."""
    s = db.get(Shipment, shipment_id)
    if not s:
        raise HTTPException(404, "Shipment not found")
    if user.role == ROLE_DRIVER and s.driver_id not in (None, user.id):
        if s.driver_id and s.driver_id != user.id:
            raise HTTPException(403, "Not your shipment")

    settings = get_settings()
    raw = await file.read()
    max_bytes = int(float(settings.upload_max_mb) * 1024 * 1024)
    if not raw:
        raise HTTPException(400, "Empty file")
    if len(raw) > max_bytes:
        raise HTTPException(400, f"File too large (max {settings.upload_max_mb} MB)")

    original = _safe_filename(file.filename or "document.bin")
    content_type = file.content_type or "application/octet-stream"
    dest_dir = _upload_root() / f"shipment_{s.id}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    stored = f"{uuid.uuid4().hex}_{original}"
    dest_path = dest_dir / stored
    dest_path.write_bytes(raw)

    if s.driver_id is None and user.role == ROLE_DRIVER:
        s.driver_id = user.id

    desc = note or f"Upload Document: {original} ({len(raw)} bytes)"
    event = ShipmentEvent(
        shipment_id=s.id,
        event_type="DOCUMENT",
        description=desc,
        location=s.origin,
        latitude=latitude,
        longitude=longitude,
        severity="info",
        document_name=original,
        document_path=str(dest_path),
        content_type=content_type,
        file_size=len(raw),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    db.refresh(s)
    return {
        "ok": True,
        "shipment": _shipment_out(db, s),
        "event": {
            "id": event.id,
            "event_type": event.event_type,
            "description": event.description,
            "document_name": event.document_name,
            "content_type": event.content_type,
            "file_size": event.file_size,
            "document_url": f"/api/shipments/{s.id}/documents/{event.id}/file",
            "timestamp": event.timestamp.isoformat() if event.timestamp else None,
        },
    }


@router.get("/shipments/{shipment_id}/documents/{event_id}/file")
def download_shipment_document(
    shipment_id: int,
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = db.get(ShipmentEvent, event_id)
    if not event or event.shipment_id != shipment_id:
        raise HTTPException(404, "Document event not found")
    s = db.get(Shipment, shipment_id)
    if not s:
        raise HTTPException(404, "Shipment not found")
    _assert_can_view_shipment(user, s)
    path = getattr(event, "document_path", None)
    if not path or not Path(path).is_file():
        raise HTTPException(404, "File missing on server")
    return FileResponse(
        path,
        media_type=event.content_type or "application/octet-stream",
        filename=event.document_name or Path(path).name,
    )


@router.get("/vehicles", response_model=list[VehicleOut])
def list_vehicles(db: Session = Depends(get_db)):
    return list(db.execute(select(Vehicle).order_by(Vehicle.id)).scalars())


@router.get("/vehicles/{vehicle_id}/location", response_model=LocationOut)
def vehicle_location(vehicle_id: int, db: Session = Depends(get_db)):
    v = db.get(Vehicle, vehicle_id)
    if not v:
        raise HTTPException(404, "Vehicle not found")
    pos = latest_vehicle_position(db, vehicle_id)
    if not pos:
        raise HTTPException(404, "No GPS fix")
    return LocationOut(
        vehicle_id=vehicle_id,
        latitude=pos.latitude,
        longitude=pos.longitude,
        speed=pos.speed,
        timestamp=pos.timestamp,
    )


@router.get("/map/overview")
def map_overview(db: Session = Depends(get_db)):
    settings = get_settings()
    weather_client = get_weather_client(settings)
    vehicles = list(db.execute(select(Vehicle)).scalars())
    markers = []
    for v in vehicles:
        pos = latest_vehicle_position(db, v.id)
        if not pos:
            continue
        wx = weather_client.get_by_coords(pos.latitude, pos.longitude).to_dict()
        ship = db.execute(
            select(Shipment)
            .where(Shipment.vehicle_id == v.id)
            .order_by(Shipment.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        pred = None
        if ship:
            pred = db.execute(
                select(LogisticsRiskPrediction)
                .where(LogisticsRiskPrediction.shipment_id == ship.id)
                .order_by(LogisticsRiskPrediction.timestamp.desc())
                .limit(1)
            ).scalar_one_or_none()
        markers.append(
            {
                "vehicle_id": v.id,
                "plate_number": v.plate_number,
                "latitude": pos.latitude,
                "longitude": pos.longitude,
                "speed": pos.speed,
                "status": v.status,
                "weather": wx,
                "shipment_id": ship.tracking_number if ship else None,
                "shipment_status": ship.status if ship else None,
                "driver": v.driver.name if v.driver else None,
                "risk_level": pred.risk_level if pred else None,
            }
        )
    shipments = list(db.execute(select(Shipment)).scalars())
    zones = []
    for s in shipments[:5]:
        zones.extend(route_risk_zones(s.origin, s.destination))
    gates = [
        {
            "id": g.id,
            "name": g.name,
            "location": g.location,
            "latitude": g.latitude,
            "longitude": g.longitude,
            "status": g.status,
        }
        for g in db.execute(select(BorderGate)).scalars()
    ]
    shipment_payloads = [_shipment_out(db, s).model_dump() for s in shipments]
    heatmap = build_risk_heatmap(
        zones=zones,
        gates=gates,
        vehicles=markers,
        shipments=shipment_payloads,
    )
    return {
        "vehicles": markers,
        "risk_zones": zones,
        "risk_heatmap": heatmap,
        "cities": list_map_cities(),
        "gates": gates,
        "corridor_weather": [],
        "weather_layers": {
            "enabled": bool(settings.openweather_api_key)
            and settings.weather_provider == "openweather",
            "provider": settings.weather_provider,
            "tiles": {
                "precipitation": "/api/weather/tiles/precipitation_new/{z}/{x}/{y}.png",
                "clouds": "/api/weather/tiles/clouds_new/{z}/{x}/{y}.png",
                "temp": "/api/weather/tiles/temp_new/{z}/{x}/{y}.png",
                "wind": "/api/weather/tiles/wind_new/{z}/{x}/{y}.png",
            },
        },
        "shipments": shipment_payloads,
    }


@router.get("/cities")
def cities():
    return list_cities()


@router.get("/locations")
def locations(db: Session = Depends(get_db)):
    """Cities (config) + border gates (DB) for shipment origin/destination pickers."""
    return list_route_locations(db)


@router.get("/routes/preview")
def preview_route(
    origin: str = Query(..., min_length=1),
    destination: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    return route_preview(db, origin, destination)


@router.get("/routes/path")
def route_path(
    origin_lat: float = Query(..., ge=-90, le=90),
    origin_lon: float = Query(..., ge=-180, le=180),
    dest_lat: float = Query(..., ge=-90, le=90),
    dest_lon: float = Query(..., ge=-180, le=180),
):
    """Road-following polyline between two coordinates (OSRM)."""
    from app.gis.routing import fetch_road_route

    road = fetch_road_route(origin_lat, origin_lon, dest_lat, dest_lon)
    return road


@router.get("/weather/point")
def weather_point(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    name: str | None = Query(default=None),
):
    settings = get_settings()
    wx = get_weather_client(settings).get_by_coords(lat, lon).to_dict()
    return {"name": name, "latitude": lat, "longitude": lon, "weather": wx}


def _reverse_geocode(lat: float, lon: float) -> dict:
    """Resolve a place name for any map click (OSM Nominatim)."""
    try:
        with httpx.Client(timeout=8.0) as client:
            resp = client.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={
                    "lat": lat,
                    "lon": lon,
                    "format": "jsonv2",
                    "zoom": 12,
                    "addressdetails": 1,
                },
                headers={"User-Agent": "MyanmarLogisticsIntelligence/1.0 (demo)"},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError:
        return {"name": f"{lat:.3f}, {lon:.3f}", "display_name": None, "address": {}}

    addr = data.get("address") or {}
    name = (
        addr.get("city")
        or addr.get("town")
        or addr.get("village")
        or addr.get("hamlet")
        or addr.get("municipality")
        or addr.get("county")
        or addr.get("state_district")
        or data.get("name")
        or f"{lat:.3f}, {lon:.3f}"
    )
    return {
        "name": str(name),
        "display_name": data.get("display_name"),
        "address": addr,
    }


@router.get("/weather/at")
def weather_at(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
):
    """Click-anywhere weather: reverse-geocode place + live weather for that point."""
    settings = get_settings()
    place = _reverse_geocode(lat, lon)
    wx = get_weather_client(settings).get_by_coords(lat, lon).to_dict()
    return {
        "name": place["name"],
        "display_name": place.get("display_name"),
        "latitude": lat,
        "longitude": lon,
        "weather": wx,
    }


_ALLOWED_OWM_LAYERS = {
    "precipitation_new",
    "clouds_new",
    "temp_new",
    "wind_new",
    "pressure_new",
}


@router.get("/weather/tiles/{layer}/{z}/{x}/{y}.png")
def weather_tile(layer: str, z: int, x: int, y: int):
    if layer not in _ALLOWED_OWM_LAYERS:
        raise HTTPException(400, f"Unsupported weather layer: {layer}")
    settings = get_settings()
    if not settings.openweather_api_key:
        raise HTTPException(503, "OPENWEATHER_API_KEY not configured")
    url = (
        f"{settings.openweather_tile_url.rstrip('/')}/{layer}/{z}/{x}/{y}.png"
        f"?appid={settings.openweather_api_key}"
    )
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Weather tile fetch failed: {exc}") from exc
    return Response(content=resp.content, media_type="image/png")


@router.post("/ai/query", response_model=AiQueryOut)
def ai_query(body: AiQueryIn, db: Session = Depends(get_db)):
    agent = LogisticsAgent(db)
    result = agent.assess(
        question=body.question,
        shipment_id=body.shipment_id,
        tracking_number=body.tracking_number,
    )
    return AiQueryOut(
        answer=str(result.get("answer") or ""),
        risk=str(result.get("risk_level") or ""),
        risk_score=float(result.get("risk_score") or 0),
        sources=result.get("sources") or [],
        recommendation=result.get("recommendation"),
        reasons=result.get("reasons") or [],
        evidence=result.get("evidence") or [],
        evidence_structured=result.get("evidence_structured") or [],
        shipment_id=result.get("shipment_id"),
        weather=result.get("weather"),
        position=result.get("position"),
        risk_zones=result.get("risk_zones") or [],
        gates=result.get("gates") or [],
        route_metrics=result.get("route_metrics"),
        osint_matched=bool(result.get("osint_matched", True)),
        fusion=result.get("fusion"),
    )


@router.post("/osint/ingest")
def osint_ingest(body: OsintIngestIn, db: Session = Depends(get_db)):
    rows = ingest_texts(db, body.texts, source=body.source)
    return {"ingested": len(rows), "ids": [r.id for r in rows]}


@router.get("/alerts")
def alerts(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(30, ge=1, le=100),
):
    # Prefer new alerts table; fall back to risk predictions
    q = select(Alert).order_by(Alert.created_at.desc())
    if user.role == ROLE_TRADER:
        ship_ids = [
            s.id
            for s in db.execute(select(Shipment).where(Shipment.trader_id == user.id)).scalars()
        ]
        if not ship_ids:
            return []
        q = q.where(Alert.shipment_id.in_(ship_ids))
    elif user.role == ROLE_DRIVER:
        ship_ids = [
            s.id
            for s in db.execute(
                select(Shipment).where(
                    (Shipment.driver_id == user.id) | (Shipment.driver_id.is_(None))
                )
            ).scalars()
        ]
        if not ship_ids:
            return []
        q = q.where(Alert.shipment_id.in_(ship_ids))
    q = q.limit(limit)
    rows = list(db.execute(q).scalars())
    if rows:
        out = []
        for a in rows:
            s = db.get(Shipment, a.shipment_id) if a.shipment_id else None
            out.append(
                {
                    "id": a.id,
                    "shipment_id": s.tracking_number if s else a.shipment_id,
                    "risk_level": a.severity,
                    "risk_score": None,
                    "explanation": a.message,
                    "timestamp": a.created_at.isoformat() if a.created_at else None,
                }
            )
        return out

    preds = list(
        db.execute(
            select(LogisticsRiskPrediction)
            .order_by(LogisticsRiskPrediction.timestamp.desc())
            .limit(limit)
        ).scalars()
    )
    out = []
    for p in preds:
        s = db.get(Shipment, p.shipment_id)
        out.append(
            {
                "id": p.id,
                "shipment_id": s.tracking_number if s else p.shipment_id,
                "risk_level": p.risk_level,
                "risk_score": p.risk_score,
                "explanation": p.explanation,
                "timestamp": p.timestamp.isoformat() if p.timestamp else None,
            }
        )
    return out
