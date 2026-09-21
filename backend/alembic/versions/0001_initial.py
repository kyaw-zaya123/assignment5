"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geography

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("company_type", sa.String(64)),
    )
    op.create_table(
        "drivers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(64)),
        sa.Column("license_no", sa.String(64)),
    )
    op.create_table(
        "vehicles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id")),
        sa.Column("driver_id", sa.Integer(), sa.ForeignKey("drivers.id")),
        sa.Column("plate_number", sa.String(64), unique=True, nullable=False),
        sa.Column("vehicle_type", sa.String(64)),
        sa.Column("capacity", sa.Float()),
        sa.Column("status", sa.String(32)),
    )
    op.create_table(
        "vehicle_positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), index=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("speed", sa.Float()),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("geom", Geography(geometry_type="POINT", srid=4326)),
    )
    op.create_table(
        "shipments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tracking_number", sa.String(64), unique=True, index=True),
        sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id")),
        sa.Column("origin", sa.String(255), nullable=False),
        sa.Column("destination", sa.String(255), nullable=False),
        sa.Column("cargo_type", sa.String(128)),
        sa.Column("weight", sa.Float()),
        sa.Column("status", sa.String(64)),
        sa.Column("origin_lat", sa.Float()),
        sa.Column("origin_lon", sa.Float()),
        sa.Column("dest_lat", sa.Float()),
        sa.Column("dest_lon", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "shipment_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shipment_id", sa.Integer(), sa.ForeignKey("shipments.id"), index=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("location", sa.String(255)),
        sa.Column("severity", sa.String(32)),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "weather_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("location", sa.String(255), nullable=False),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("temperature", sa.Float()),
        sa.Column("rainfall", sa.Float()),
        sa.Column("humidity", sa.Float()),
        sa.Column("condition", sa.String(128)),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "osint_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(128)),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("content", sa.Text()),
        sa.Column("event_type", sa.String(64)),
        sa.Column("location", sa.String(255)),
        sa.Column("severity", sa.String(32)),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "logistics_risk_predictions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shipment_id", sa.Integer(), sa.ForeignKey("shipments.id"), index=True),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("risk_level", sa.String(32), nullable=False),
        sa.Column("explanation", sa.Text()),
        sa.Column("model", sa.String(128)),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    for table in (
        "logistics_risk_predictions",
        "osint_events",
        "weather_observations",
        "shipment_events",
        "shipments",
        "vehicle_positions",
        "vehicles",
        "drivers",
        "companies",
    ):
        op.drop_table(table)
