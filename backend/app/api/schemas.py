from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ShipmentCreate(BaseModel):
    tracking_number: Optional[str] = None
    vehicle_id: Optional[int] = None
    trader_id: Optional[int] = None
    driver_id: Optional[int] = None
    origin: str
    destination: str
    cargo_type: Optional[str] = None
    weight: Optional[float] = None
    status: str = "CREATED"
    origin_lat: Optional[float] = None
    origin_lon: Optional[float] = None
    dest_lat: Optional[float] = None
    dest_lon: Optional[float] = None


class ShipmentOut(BaseModel):
    id: int
    tracking_number: str
    vehicle_id: Optional[int]
    trader_id: Optional[int] = None
    driver_id: Optional[int] = None
    origin: str
    destination: str
    cargo_type: Optional[str]
    weight: Optional[float]
    status: str
    origin_lat: Optional[float] = None
    origin_lon: Optional[float] = None
    dest_lat: Optional[float] = None
    dest_lon: Optional[float] = None
    latest_risk_level: Optional[str] = None
    latest_risk_score: Optional[float] = None

    model_config = {"from_attributes": True}


class VehicleOut(BaseModel):
    id: int
    plate_number: str
    vehicle_type: str
    capacity: Optional[float]
    status: str
    company_id: Optional[int]
    driver_id: Optional[int]

    model_config = {"from_attributes": True}


class LocationOut(BaseModel):
    vehicle_id: int
    latitude: float
    longitude: float
    speed: Optional[float]
    timestamp: Optional[datetime]


class AiQueryIn(BaseModel):
    question: str = Field(..., min_length=3)
    shipment_id: Optional[int] = None
    tracking_number: Optional[str] = None


class AiQueryOut(BaseModel):
    answer: str
    risk: str
    risk_score: float
    sources: list[dict[str, Any]]
    recommendation: Optional[str] = None
    reasons: list[str] = []
    evidence: list[Any] = []
    evidence_structured: list[dict[str, Any]] = []
    shipment_id: Optional[str] = None
    weather: Optional[dict[str, Any]] = None
    position: Optional[dict[str, Any]] = None
    risk_zones: list[dict[str, Any]] = []
    gates: list[dict[str, Any]] = []
    route_metrics: Optional[dict[str, Any]] = None
    osint_matched: bool = True
    fusion: Optional[str] = None


class OsintIngestIn(BaseModel):
    texts: list[str]
    source: str = "manual"
