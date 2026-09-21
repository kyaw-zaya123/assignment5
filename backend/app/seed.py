"""Seed Myanmar corridor demo + RBAC users + border gates."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from geoalchemy2.elements import WKTElement
from sqlalchemy import select

from app.core.security import hash_password
from app.database.models import (
    Alert,
    BorderGate,
    Company,
    Driver,
    OsintEvent,
    Shipment,
    ShipmentEvent,
    User,
    Vehicle,
    VehiclePosition,
    WeatherObservation,
)
from app.database.postgres import Base, SessionLocal, engine, ensure_postgis
from app.osint.processor import process_text

# Major Myanmar land / sea border gates & trade ports (shown on map)
GATES = [
    ("Muse", "Muse–Ruili (China)", 23.9780, 97.9040, "OPEN"),
    ("Chinshwehaw", "Chinshwehaw–Qingshuihe (China)", 23.9330, 97.7500, "OPEN"),
    ("Lweje", "Lweje–Zhangfeng (China)", 24.2160, 97.3000, "OPEN"),
    ("Kanpiketi", "Kanpiketi–Houqiao (China)", 24.7500, 97.5500, "OPEN"),
    ("Tamu", "Tamu–Moreh (India)", 24.2153, 94.3100, "OPEN"),
    ("Reed", "Reed / Rihkhawdar (India)", 23.2500, 93.3500, "OPEN"),
    ("Myawaddy", "Myawaddy–Mae Sot (Thailand)", 16.6897, 98.5089, "OPEN"),
    ("Tachileik", "Tachileik–Mae Sai (Thailand)", 20.4492, 99.8808, "WARNING"),
    ("Kawthaung", "Kawthaung–Ranong (Thailand)", 9.9822, 98.5503, "OPEN"),
    ("Htee Kee", "Htee Kee–Phu Nam Ron (Thailand)", 14.1500, 98.7000, "OPEN"),
    ("Maungdaw", "Maungdaw–Teknaf corridor (Bangladesh)", 20.8167, 92.3667, "WARNING"),
    ("Sittwe Port", "Sittwe Port (Rakhine)", 20.1462, 92.8984, "OPEN"),
    ("Yangon Port", "Yangon Port / Thilawa", 16.7667, 96.1667, "OPEN"),
]


def seed() -> None:
    with engine.begin() as conn:
        ensure_postgis(conn)
        Base.metadata.create_all(bind=conn)

    db = SessionLocal()
    try:
        # Users
        users = {
            "admin": ("ADMIN", "Admin123!", "System Admin"),
            "trader": ("TRADER", "Trader123!", "Ayeyarwady Trader"),
            "driver1": ("DRIVER", "Driver123!", "Ko Aung"),
        }
        user_rows: dict[str, User] = {}
        for username, (role, password, display) in users.items():
            u = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
            if not u:
                u = User(
                    username=username,
                    password_hash=hash_password(password),
                    role=role,
                    display_name=display,
                )
                db.add(u)
                db.flush()
            user_rows[username] = u

        for name, location, lat, lon, status in GATES:
            g = db.execute(select(BorderGate).where(BorderGate.name == name)).scalar_one_or_none()
            if not g:
                db.add(
                    BorderGate(
                        name=name,
                        location=location,
                        latitude=lat,
                        longitude=lon,
                        status=status,
                    )
                )
            else:
                # Keep coords/labels fresh; do not overwrite live OPEN/WARNING/CLOSED demos
                g.location = location
                g.latitude = lat
                g.longitude = lon

        existing = db.execute(
            select(Shipment).where(Shipment.tracking_number == "SH001")
        ).scalar_one_or_none()
        if existing:
            # attach ownership if missing
            if existing.trader_id is None:
                existing.trader_id = user_rows["trader"].id
            if existing.driver_id is None:
                existing.driver_id = user_rows["driver1"].id
            if (existing.status or "").lower() == "in_transit":
                existing.status = "IN_TRANSIT"
            # Repair SH002 + any orphan demo rows so trader/driver consoles stay usable
            for tracking in ("SH002",):
                row = db.execute(
                    select(Shipment).where(Shipment.tracking_number == tracking)
                ).scalar_one_or_none()
                if not row:
                    continue
                if row.trader_id is None:
                    row.trader_id = user_rows["trader"].id
                if row.driver_id is None:
                    row.driver_id = user_rows["driver1"].id
            # Link Driver profile to user if seed created Driver before user_id column
            drv = db.execute(
                select(Driver).where(Driver.name == "Ko Aung")
            ).scalar_one_or_none()
            if drv and getattr(drv, "user_id", None) is None:
                drv.user_id = user_rows["driver1"].id
            db.commit()
            print("Demo data already present (SH001). Users/gates/ownership ensured.")
            return

        company = Company(name="Ayeyarwady Trade Co.", company_type="trader")
        driver = Driver(
            name="Ko Aung",
            phone="+959123456789",
            license_no="MD-99881",
            user_id=user_rows["driver1"].id,
        )
        db.add_all([company, driver])
        db.flush()

        vehicle = Vehicle(
            company_id=company.id,
            driver_id=driver.id,
            plate_number="YGN-7H-4421",
            vehicle_type="truck",
            capacity=18.0,
            status="in_transit",
        )
        db.add(vehicle)
        db.flush()

        trail = [
            (16.8409, 96.1735, 42),
            (16.92, 96.55, 48),
            (17.05, 97.10, 51),
            (16.95, 97.70, 38),
            (16.78, 98.15, 35),
            (16.72, 98.35, 28),
        ]
        now = datetime.now(timezone.utc)
        for i, (lat, lon, speed) in enumerate(trail):
            db.add(
                VehiclePosition(
                    vehicle_id=vehicle.id,
                    latitude=lat,
                    longitude=lon,
                    speed=speed,
                    timestamp=now - timedelta(hours=len(trail) - i),
                    geom=WKTElement(f"POINT({lon} {lat})", srid=4326),
                )
            )

        shipment = Shipment(
            tracking_number="SH001",
            vehicle_id=vehicle.id,
            trader_id=user_rows["trader"].id,
            driver_id=user_rows["driver1"].id,
            origin="Yangon",
            destination="Myawaddy",
            cargo_type="electronics",
            weight=12.5,
            status="IN_TRANSIT",
            origin_lat=16.8409,
            origin_lon=96.1735,
            dest_lat=16.6897,
            dest_lon=98.5089,
        )
        db.add(shipment)
        db.flush()

        db.add_all(
            [
                ShipmentEvent(
                    shipment_id=shipment.id,
                    event_type="CREATED",
                    description="Shipment created by trader",
                    location="Yangon",
                    severity="info",
                ),
                ShipmentEvent(
                    shipment_id=shipment.id,
                    event_type="PICKED_UP",
                    description="Picked up from Yangon warehouse",
                    location="Yangon Warehouse",
                    latitude=16.8409,
                    longitude=96.1735,
                    severity="info",
                ),
                ShipmentEvent(
                    shipment_id=shipment.id,
                    event_type="IN_TRANSIT",
                    description="Trip started toward Myawaddy",
                    location="Yangon",
                    severity="info",
                ),
            ]
        )

        db.add(
            WeatherObservation(
                location="Near Myawaddy",
                latitude=16.72,
                longitude=98.35,
                temperature=27.5,
                rainfall=42.0,
                humidity=91.0,
                condition="heavy_rain",
            )
        )

        for t in [
            "Flood blocks Myawaddy highway after overnight rainfall",
            "Temporary checkpoint delays reported on Asia Highway toward Mae Sot",
            "Muse border trade resumes with intermittent closures",
        ]:
            db.add(OsintEvent(**process_text(t, source="seed")))

        v2 = Vehicle(
            company_id=company.id,
            plate_number="MDY-3K-1102",
            vehicle_type="truck",
            capacity=20.0,
            status="active",
        )
        db.add(v2)
        db.flush()
        db.add(
            VehiclePosition(
                vehicle_id=v2.id,
                latitude=21.9588,
                longitude=96.0891,
                speed=0,
                timestamp=now,
                geom=WKTElement("POINT(96.0891 21.9588)", srid=4326),
            )
        )
        db.add(
            Shipment(
                tracking_number="SH002",
                vehicle_id=v2.id,
                trader_id=user_rows["trader"].id,
                origin="Mandalay",
                destination="Muse",
                cargo_type="agricultural",
                weight=15.0,
                status="CREATED",
                origin_lat=21.9588,
                origin_lon=96.0891,
                dest_lat=23.9780,
                dest_lon=97.9040,
            )
        )

        db.add(
            Alert(
                shipment_id=shipment.id,
                severity="MEDIUM",
                message="Demo alert: monitor Myawaddy corridor weather and OSINT.",
            )
        )

        db.commit()
        print("Seeded SH001/SH002 + users (admin/trader/driver1) + border gates.")
        print("  admin/Admin123!  trader/Trader123!  driver1/Driver123!")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
