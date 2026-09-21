"""Border gate management + affected shipment alerts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.security import ROLE_ADMIN, get_current_user, require_roles
from app.database.models import Alert, BorderGate, Shipment, User
from app.database.postgres import get_db
from app.intelligence.agents.logistics_agent import LogisticsAgent

router = APIRouter(prefix="/gates", tags=["gates"])


class GateOut(BaseModel):
    id: int
    name: str
    location: str
    latitude: float | None
    longitude: float | None
    status: str
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class GateStatusIn(BaseModel):
    status: str = Field(..., pattern="^(OPEN|WARNING|CLOSED)$")


class AffectedShipmentOut(BaseModel):
    id: int
    tracking_number: str
    origin: str
    destination: str
    status: str
    alert_severity: str | None = None
    risk_level: str | None = None
    risk_score: float | None = None
    recommendation: str | None = None
    evidence: list[Any] = []
    evidence_structured: list[dict[str, Any]] = []
    answer: str | None = None


class GateUpdateResult(BaseModel):
    gate: GateOut
    previous_status: str
    new_status: str
    affected_count: int
    ai_ran: bool
    affected_shipments: list[AffectedShipmentOut]
    summary: str


@router.get("", response_model=list[GateOut])
def list_gates(db: Session = Depends(get_db)):
    return list(db.execute(select(BorderGate).order_by(BorderGate.name)).scalars())


@router.patch("/{gate_id}", response_model=GateUpdateResult)
def update_gate(
    gate_id: int,
    body: GateStatusIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(ROLE_ADMIN)),
):
    gate = db.get(BorderGate, gate_id)
    if not gate:
        raise HTTPException(404, "Gate not found")
    old = gate.status
    gate.status = body.status
    gate.updated_at = datetime.now(timezone.utc)
    db.add(gate)

    name = gate.name
    affected = list(
        db.execute(
            select(Shipment).where(
                or_(
                    Shipment.origin.ilike(f"%{name}%"),
                    Shipment.destination.ilike(f"%{name}%"),
                ),
                Shipment.status.notin_(["DELIVERED"]),
            )
        ).scalars()
    )

    agent = LogisticsAgent(db)
    results: list[AffectedShipmentOut] = []
    ai_ran = body.status in {"CLOSED", "WARNING"}

    for s in affected:
        severity = (
            "HIGH" if body.status == "CLOSED" else "MEDIUM" if body.status == "WARNING" else "LOW"
        )
        msg = (
            f"Border gate {gate.name} changed {old} → {body.status}. "
            f"Shipment {s.tracking_number} ({s.origin} → {s.destination}) may be affected."
        )
        db.add(Alert(shipment_id=s.id, severity=severity, message=msg))

        row = AffectedShipmentOut(
            id=s.id,
            tracking_number=s.tracking_number,
            origin=s.origin,
            destination=s.destination,
            status=s.status,
            alert_severity=severity,
        )
        if ai_ran:
            analysis = agent.assess(
                question=(
                    f"Check risk for shipment {s.tracking_number} after "
                    f"{gate.name} gate {body.status}"
                ),
                shipment_id=s.id,
            )
            row.risk_level = str(analysis.get("risk_level") or "")
            try:
                row.risk_score = float(analysis.get("risk_score"))
            except (TypeError, ValueError):
                row.risk_score = None
            row.recommendation = analysis.get("recommendation")
            row.evidence = analysis.get("evidence") or []
            row.evidence_structured = analysis.get("evidence_structured") or []
            ans = analysis.get("answer")
            row.answer = ans if isinstance(ans, str) else str(ans) if ans is not None else None
        results.append(row)

    db.commit()
    db.refresh(gate)

    if not affected:
        summary = (
            f"{gate.name}: {old} → {body.status}. No active shipments on this corridor."
        )
    elif ai_ran:
        summary = (
            f"{gate.name}: {old} → {body.status}. "
            f"{len(results)} shipment(s) alerted; AI risk analysis completed."
        )
    else:
        summary = (
            f"{gate.name}: {old} → {body.status}. "
            f"{len(results)} shipment(s) notified (LOW)."
        )

    return GateUpdateResult(
        gate=GateOut.model_validate(gate),
        previous_status=old,
        new_status=body.status,
        affected_count=len(results),
        ai_ran=ai_ran,
        affected_shipments=results,
        summary=summary,
    )


@router.get("/{gate_id}/impact")
def gate_impact(gate_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    gate = db.get(BorderGate, gate_id)
    if not gate:
        raise HTTPException(404, "Gate not found")
    affected = list(
        db.execute(
            select(Shipment).where(
                or_(
                    Shipment.origin.ilike(f"%{gate.name}%"),
                    Shipment.destination.ilike(f"%{gate.name}%"),
                ),
                Shipment.status.notin_(["DELIVERED"]),
            )
        ).scalars()
    )
    return {
        "gate": GateOut.model_validate(gate),
        "affected_shipments": [
            {
                "id": s.id,
                "tracking_number": s.tracking_number,
                "origin": s.origin,
                "destination": s.destination,
                "status": s.status,
            }
            for s in affected
        ],
    }
