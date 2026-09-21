"""Add shipment document attachment fields on shipment_events.

Revision ID: 0003_documents
Revises: 0002_rbac
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0003_documents"
down_revision: Union[str, None] = "0002_rbac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns(table)}
    return column in cols


def upgrade() -> None:
    if not _has_column("shipment_events", "document_name"):
        op.add_column("shipment_events", sa.Column("document_name", sa.String(255)))
    if not _has_column("shipment_events", "document_path"):
        op.add_column("shipment_events", sa.Column("document_path", sa.String(512)))
    if not _has_column("shipment_events", "content_type"):
        op.add_column("shipment_events", sa.Column("content_type", sa.String(128)))
    if not _has_column("shipment_events", "file_size"):
        op.add_column("shipment_events", sa.Column("file_size", sa.Integer()))


def downgrade() -> None:
    if _has_column("shipment_events", "file_size"):
        op.drop_column("shipment_events", "file_size")
    if _has_column("shipment_events", "content_type"):
        op.drop_column("shipment_events", "content_type")
    if _has_column("shipment_events", "document_path"):
        op.drop_column("shipment_events", "document_path")
    if _has_column("shipment_events", "document_name"):
        op.drop_column("shipment_events", "document_name")
