"""SQLAlchemy / PostGIS domain models — extended for RBAC prototype."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from geoalchemy2 import Geography
from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.postgres import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # ADMIN|TRADER|DRIVER
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    company_type: Mapped[str] = mapped_column(String(64), default="trader")

    vehicles: Mapped[list["Vehicle"]] = relationship(back_populates="company")


class Driver(Base):
    __tablename__ = "drivers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(64))
    license_no: Mapped[Optional[str]] = mapped_column(String(64))
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), index=True)

    vehicles: Mapped[list["Vehicle"]] = relationship(back_populates="driver")


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[Optional[int]] = mapped_column(ForeignKey("companies.id"))
    driver_id: Mapped[Optional[int]] = mapped_column(ForeignKey("drivers.id"))
    plate_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    vehicle_type: Mapped[str] = mapped_column(String(64), default="truck")
    capacity: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), default="active")

    company: Mapped[Optional[Company]] = relationship(back_populates="vehicles")
    driver: Mapped[Optional[Driver]] = relationship(back_populates="vehicles")
    positions: Mapped[list["VehiclePosition"]] = relationship(back_populates="vehicle")
    shipments: Mapped[list["Shipment"]] = relationship(back_populates="vehicle")


class VehiclePosition(Base):
    __tablename__ = "vehicle_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    speed: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    geom = mapped_column(
        Geography(geometry_type="POINT", srid=4326),
        nullable=True,
    )

    vehicle: Mapped[Vehicle] = relationship(back_populates="positions")


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tracking_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    vehicle_id: Mapped[Optional[int]] = mapped_column(ForeignKey("vehicles.id"))
    trader_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), index=True)
    driver_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), index=True)
    origin: Mapped[str] = mapped_column(String(255), nullable=False)
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    cargo_type: Mapped[Optional[str]] = mapped_column(String(128))
    weight: Mapped[Optional[float]] = mapped_column(Float)
    # CREATED|PICKED_UP|IN_TRANSIT|CHECKPOINT|CUSTOMS|DELIVERED|DELAYED
    status: Mapped[str] = mapped_column(String(64), default="CREATED")
    origin_lat: Mapped[Optional[float]] = mapped_column(Float)
    origin_lon: Mapped[Optional[float]] = mapped_column(Float)
    dest_lat: Mapped[Optional[float]] = mapped_column(Float)
    dest_lon: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    vehicle: Mapped[Optional[Vehicle]] = relationship(back_populates="shipments")
    events: Mapped[list["ShipmentEvent"]] = relationship(back_populates="shipment")
    risk_predictions: Mapped[list["LogisticsRiskPrediction"]] = relationship(
        back_populates="shipment"
    )
    alerts: Mapped[list["Alert"]] = relationship(back_populates="shipment")


class ShipmentEvent(Base):
    __tablename__ = "shipment_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    location: Mapped[Optional[str]] = mapped_column(String(255))
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String(32), default="info")
    document_name: Mapped[Optional[str]] = mapped_column(String(255))
    document_path: Mapped[Optional[str]] = mapped_column(String(512))
    content_type: Mapped[Optional[str]] = mapped_column(String(128))
    file_size: Mapped[Optional[int]] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    shipment: Mapped[Shipment] = relationship(back_populates="events")


class BorderGate(Base):
    __tablename__ = "border_gates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), default="OPEN")  # OPEN|WARNING|CLOSED
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shipment_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("shipments.id"), index=True
    )
    severity: Mapped[str] = mapped_column(String(32), default="MEDIUM")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    shipment: Mapped[Optional[Shipment]] = relationship(back_populates="alerts")


class WeatherObservation(Base):
    __tablename__ = "weather_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)
    temperature: Mapped[Optional[float]] = mapped_column(Float)
    rainfall: Mapped[Optional[float]] = mapped_column(Float)
    humidity: Mapped[Optional[float]] = mapped_column(Float)
    condition: Mapped[Optional[str]] = mapped_column(String(128))
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OsintEvent(Base):
    __tablename__ = "osint_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(128), default="manual")
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(String(64), default="unknown")
    location: Mapped[Optional[str]] = mapped_column(String(255))
    severity: Mapped[str] = mapped_column(String(32), default="medium")
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LogisticsRiskPrediction(Base):
    __tablename__ = "logistics_risk_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"), index=True)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    explanation: Mapped[Optional[str]] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(128), default="hybrid")
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    shipment: Mapped[Shipment] = relationship(back_populates="risk_predictions")
