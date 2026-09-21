"""OSINT crawler stub — v1 uses Qdrant read + manual ingest."""

from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy.orm import Session

from app.database.models import OsintEvent
from app.osint.processor import process_text

logger = logging.getLogger(__name__)


def ingest_texts(db: Session, texts: Iterable[str], source: str = "manual") -> list[OsintEvent]:
    created: list[OsintEvent] = []
    for text in texts:
        parsed = process_text(text, source=source)
        row = OsintEvent(**parsed)
        db.add(row)
        created.append(row)
    db.commit()
    for row in created:
        db.refresh(row)
    logger.info("Ingested %s OSINT events from %s", len(created), source)
    return created
