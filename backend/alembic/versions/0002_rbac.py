"""RBAC extension — users, gates, alerts, shipment ownership.

Revision ID: 0002_rbac
Revises: 0001_initial
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0002_rbac"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return inspect(bind).has_table(name)


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns(table)}
    return column in cols


def _has_index(table: str, index: str) -> bool:
    bind = op.get_bind()
    return any(i["name"] == index for i in inspect(bind).get_indexes(table))


def upgrade() -> None:
    if not _has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("username", sa.String(64), nullable=False),
            sa.Column("password_hash", sa.String(255), nullable=False),
            sa.Column("role", sa.String(32), nullable=False),
            sa.Column("display_name", sa.String(255)),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
        )
    if not _has_index("users", "ix_users_username"):
        op.create_index("ix_users_username", "users", ["username"], unique=True)

    if not _has_table("border_gates"):
        op.create_table(
            "border_gates",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(128), nullable=False, unique=True),
            sa.Column("location", sa.String(255), nullable=False),
            sa.Column("latitude", sa.Float()),
            sa.Column("longitude", sa.Float()),
            sa.Column("status", sa.String(32), server_default="OPEN"),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
        )

    if not _has_table("alerts"):
        op.create_table(
            "alerts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "shipment_id",
                sa.Integer(),
                sa.ForeignKey("shipments.id"),
                index=True,
            ),
            sa.Column("severity", sa.String(32), server_default="MEDIUM"),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
        )

    if not _has_column("shipments", "trader_id"):
        op.add_column(
            "shipments",
            sa.Column("trader_id", sa.Integer(), sa.ForeignKey("users.id")),
        )
    if not _has_column("shipments", "driver_id"):
        op.add_column(
            "shipments",
            sa.Column("driver_id", sa.Integer(), sa.ForeignKey("users.id")),
        )
    if not _has_index("shipments", "ix_shipments_trader_id"):
        op.create_index("ix_shipments_trader_id", "shipments", ["trader_id"])
    if not _has_index("shipments", "ix_shipments_driver_id"):
        op.create_index("ix_shipments_driver_id", "shipments", ["driver_id"])

    if not _has_column("shipment_events", "latitude"):
        op.add_column("shipment_events", sa.Column("latitude", sa.Float()))
    if not _has_column("shipment_events", "longitude"):
        op.add_column("shipment_events", sa.Column("longitude", sa.Float()))

    if not _has_column("drivers", "user_id"):
        op.add_column(
            "drivers",
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")),
        )
    if not _has_index("drivers", "ix_drivers_user_id"):
        op.create_index("ix_drivers_user_id", "drivers", ["user_id"])


def downgrade() -> None:
    if _has_index("drivers", "ix_drivers_user_id"):
        op.drop_index("ix_drivers_user_id", table_name="drivers")
    if _has_column("drivers", "user_id"):
        op.drop_column("drivers", "user_id")
    if _has_column("shipment_events", "longitude"):
        op.drop_column("shipment_events", "longitude")
    if _has_column("shipment_events", "latitude"):
        op.drop_column("shipment_events", "latitude")
    if _has_index("shipments", "ix_shipments_driver_id"):
        op.drop_index("ix_shipments_driver_id", table_name="shipments")
    if _has_index("shipments", "ix_shipments_trader_id"):
        op.drop_index("ix_shipments_trader_id", table_name="shipments")
    if _has_column("shipments", "driver_id"):
        op.drop_column("shipments", "driver_id")
    if _has_column("shipments", "trader_id"):
        op.drop_column("shipments", "trader_id")
    if _has_table("alerts"):
        op.drop_table("alerts")
    if _has_table("border_gates"):
        op.drop_table("border_gates")
    if _has_index("users", "ix_users_username"):
        op.drop_index("ix_users_username", table_name="users")
    if _has_table("users"):
        op.drop_table("users")
