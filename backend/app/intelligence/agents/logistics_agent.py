"""Logistics Decision Agent — tools first, then Gemma explanation."""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.models import BorderGate, LogisticsRiskPrediction, Shipment, ShipmentEvent
from app.gis.eta import estimate_route_metrics, resolve_map_corridor
from app.gis.spatial import infer_corridor_coords, latest_vehicle_position, route_risk_zones
from app.intelligence.llm.gemma_client import GemmaClient
from app.intelligence.rag.context_builder import build_context, fuse_answer, prefer_myanmar
from app.intelligence.rag.reranker import parse_hit_timestamp, select_semantic_osint
from app.intelligence.rag.retriever import QdrantService
from app.weather.weather_client import get_weather_client

logger = logging.getLogger(__name__)


def detect_intent(question: str) -> str:
    q = question.lower()
    if any(
        k in q
        for k in (
            "ကြာ",
            "ပို့ချိန်",
            "ဘယ်လောက်",
            "eta",
            "how long",
            "duration",
            "delivery time",
            "hours",
        )
    ):
        return "eta"
    if any(k in q for k in ("where", "location", "gps")):
        return "location"
    if any(k in q for k in ("delay", "late")):
        return "delay"
    if any(k in q for k in ("risk", "safe", "danger", "flood", "closure", "gate")):
        return "risk"
    if any(k in q for k in ("alternative", "reroute", "recommend")):
        return "action"
    return "general"


def extract_shipment_ref(question: str) -> str | None:
    m = re.search(r"\b(SH\d{3,}|MM[A-Z0-9]+)\b", question, re.I)
    return m.group(1).upper() if m else None


def heuristic_risk(
    *,
    weather: dict[str, Any] | None,
    osint_hits: list[dict[str, Any]],
    shipment_status: str | None,
    gates: list[dict[str, Any]] | None = None,
    position: dict[str, Any] | None = None,
    route_metrics: dict[str, Any] | None = None,
    osint_matched: bool = True,
) -> dict[str, Any]:
    score = 0.15
    reasons: list[str] = []
    evidence: list[dict[str, Any]] = []

    if weather:
        rain = weather.get("rainfall") or 0
        if weather.get("flood_risk") == "high" or rain >= 30:
            score += 0.35
            reasons.append("Heavy rainfall / high flood risk on corridor")
            evidence.append(
                {
                    "source": "Weather API",
                    "detail": f"Rainfall={rain} mm, flood_risk={weather.get('flood_risk')}, condition={weather.get('condition')}",
                }
            )
        elif weather.get("flood_risk") == "medium" or rain >= 5:
            score += 0.15
            reasons.append("Elevated rainfall")
            evidence.append(
                {
                    "source": "Weather API",
                    "detail": f"Rainfall={rain} mm, flood_risk={weather.get('flood_risk')}, condition={weather.get('condition')}",
                }
            )
        else:
            evidence.append(
                {
                    "source": "Weather API",
                    "detail": f"condition={weather.get('condition')}, rain={rain} mm, flood_risk={weather.get('flood_risk')}, temp={weather.get('temperature')}°C",
                }
            )
        if weather.get("storm"):
            score += 0.15
            reasons.append("Storm conditions")

    if route_metrics:
        evidence.append(
            {
                "source": "Map",
                "detail": (
                    f"{route_metrics.get('origin')}→{route_metrics.get('destination')}: "
                    f"≈{route_metrics.get('road_km')} km road "
                    f"(straight {route_metrics.get('straight_km')} km), "
                    f"ETA {route_metrics.get('eta_text')} "
                    f"({route_metrics.get('weather_note')})"
                ),
            }
        )
        reasons.append(
            f"Map ≈{route_metrics.get('road_km')} km; ETA {route_metrics.get('eta_text')}"
        )

    if gates:
        for g in gates:
            st = (g.get("status") or "OPEN").upper()
            if st == "CLOSED":
                score += 0.35
                reasons.append(f"{g.get('name')} gate CLOSED")
                evidence.append(
                    {"source": "Border Gate", "detail": f"{g.get('name')} status=CLOSED"}
                )
            elif st == "WARNING":
                score += 0.2
                reasons.append(f"{g.get('name')} gate WARNING")
                evidence.append(
                    {"source": "Border Gate", "detail": f"{g.get('name')} status=WARNING"}
                )

    risk_kw = ("flood", "closure", "block", "conflict", "landslide", "တိုက်ပွဲ", "ရေကြီး")
    osint_hits_risk = 0
    dated_hits = sorted(osint_hits, key=parse_hit_timestamp, reverse=True) if osint_matched else []
    for h in dated_hits:
        text = str(h.get("text") or "").lower()
        if any(k in text for k in risk_kw):
            osint_hits_risk += 1
    if osint_hits_risk:
        score += min(0.35, 0.12 * osint_hits_risk)
        reasons.append(f"OSINT risk signals ({osint_hits_risk} hits, newest-first)")
    if dated_hits:
        for h in dated_hits[:3]:
            snippet = (h.get("text") or "").replace("\n", " ").strip()[:140]
            evidence.append(
                {
                    "source": "Qdrant OSINT",
                    "detail": f"[{h.get('date') or 'undated'}] {snippet}",
                }
            )
    else:
        evidence.append(
            {
                "source": "Qdrant OSINT",
                "detail": (
                    "No semantic OSINT in the last 7 days — "
                    "fallback to Weather API + map ETA + LLM knowledge"
                ),
            }
        )

    if position and (position.get("speed") or 0) < 15:
        evidence.append(
            {
                "source": "GPS",
                "detail": f"Vehicle speed reduced to {position.get('speed')} km/h",
            }
        )
        score += 0.05

    status_u = (shipment_status or "").upper()
    if status_u in {"DELAYED", "EXCEPTION", "HELD"}:
        score += 0.15
        reasons.append(f"Shipment status={shipment_status}")
        evidence.append({"source": "Shipment status", "detail": status_u})

    score = max(0.0, min(1.0, score))
    if score >= 0.7:
        level = "HIGH"
    elif score >= 0.4:
        level = "MEDIUM"
    else:
        level = "LOW"
    if not reasons:
        reasons.append("No major weather, gate, or OSINT risk signals")
    recommendation = {
        "HIGH": "Consider delaying departure or use alternative route; notify traders",
        "MEDIUM": "Increase GPS polling and monitor checkpoints / gate status",
        "LOW": "Continue planned route with standard monitoring",
    }[level]
    if route_metrics:
        recommendation = (
            f"Plan for {route_metrics.get('eta_text')} "
            f"(≈{route_metrics.get('road_km')} km). {recommendation}"
        )
    return {
        "risk_score": round(score, 3),
        "risk_level": level,
        "reasons": reasons,
        "recommendation": recommendation,
        "evidence": evidence,
    }


class LogisticsAgent:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.qdrant = QdrantService(self.settings)
        self.weather = get_weather_client(self.settings)
        self.llm = GemmaClient(self.settings)

    def _get_shipment(self, shipment_id: int | None, tracking: str | None) -> Shipment | None:
        if shipment_id is not None:
            return self.db.get(Shipment, shipment_id)
        if tracking:
            stmt = select(Shipment).where(Shipment.tracking_number == tracking)
            return self.db.execute(stmt).scalar_one_or_none()
        return None

    def _relevant_gates(self, shipment: Shipment | None) -> list[dict[str, Any]]:
        gates = list(self.db.execute(select(BorderGate)).scalars())
        if not shipment:
            return [
                {
                    "name": g.name,
                    "status": g.status,
                    "location": g.location,
                    "latitude": g.latitude,
                    "longitude": g.longitude,
                }
                for g in gates
            ]
        route = f"{shipment.origin} {shipment.destination}".lower()
        out = []
        for g in gates:
            if g.name.lower() in route or g.status != "OPEN":
                out.append(
                    {
                        "name": g.name,
                        "status": g.status,
                        "location": g.location,
                        "latitude": g.latitude,
                        "longitude": g.longitude,
                    }
                )
        return out or [
            {
                "name": g.name,
                "status": g.status,
                "location": g.location,
                "latitude": g.latitude,
                "longitude": g.longitude,
            }
            for g in gates
        ]

    def assess(
        self,
        *,
        question: str,
        shipment_id: int | None = None,
        tracking_number: str | None = None,
    ) -> dict[str, Any]:
        intent = detect_intent(question)
        tracking_number = tracking_number or extract_shipment_ref(question)
        shipment = self._get_shipment(shipment_id, tracking_number)

        shipment_dict = None
        position_dict = None
        events_list: list[dict[str, Any]] = []
        lat = lon = None
        if shipment:
            shipment_dict = {
                "id": shipment.id,
                "tracking_number": shipment.tracking_number,
                "status": shipment.status,
                "origin": shipment.origin,
                "destination": shipment.destination,
                "cargo_type": shipment.cargo_type,
                "weight": shipment.weight,
                "vehicle_id": shipment.vehicle_id,
            }
            if shipment.vehicle_id:
                pos = latest_vehicle_position(self.db, shipment.vehicle_id)
                if pos:
                    lat, lon = pos.latitude, pos.longitude
                    position_dict = {
                        "latitude": pos.latitude,
                        "longitude": pos.longitude,
                        "speed": pos.speed,
                        "timestamp": pos.timestamp.isoformat() if pos.timestamp else None,
                    }
            if lat is None:
                coords = infer_corridor_coords(shipment.destination) or infer_corridor_coords(
                    shipment.origin
                )
                if coords:
                    lat, lon = coords

            evs = list(
                self.db.execute(
                    select(ShipmentEvent)
                    .where(ShipmentEvent.shipment_id == shipment.id)
                    .order_by(ShipmentEvent.timestamp.desc())
                    .limit(10)
                ).scalars()
            )
            events_list = [
                {
                    "event_type": e.event_type,
                    "description": e.description,
                    "location": e.location,
                    "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                }
                for e in evs
            ]

        weather_dict = None
        if lat is not None and lon is not None:
            weather_dict = self.weather.get_by_coords(lat, lon).to_dict()
        elif shipment:
            # Shipment endpoints only (no alias tables) — for Weather API point
            coords = infer_corridor_coords(shipment.destination) or infer_corridor_coords(
                shipment.origin
            )
            if coords:
                weather_dict = self.weather.get_by_coords(coords[0], coords[1]).to_dict()

        gates = self._relevant_gates(shipment)

        origin_name, dest_name = resolve_map_corridor(
            self.db,
            question,
            shipment.origin if shipment else None,
            shipment.destination if shipment else None,
        )
        route_metrics = estimate_route_metrics(
            self.db, origin_name, dest_name, weather=weather_dict
        )
        # Prefer mid-corridor weather when we have map endpoints
        if route_metrics:
            mid_lat = (route_metrics["origin_lat"] + route_metrics["dest_lat"]) / 2
            mid_lon = (route_metrics["origin_lon"] + route_metrics["dest_lon"]) / 2
            weather_dict = self.weather.get_by_coords(mid_lat, mid_lon).to_dict()
            route_metrics = estimate_route_metrics(
                self.db, origin_name, dest_name, weather=weather_dict
            )

        route_hint = ""
        if origin_name or dest_name:
            route_hint = f"{origin_name or ''} {dest_name or ''}".strip()
        elif shipment:
            route_hint = f"{shipment.origin} {shipment.destination}"
        weather_terms = ""
        if weather_dict:
            if weather_dict.get("flood_risk") in {"medium", "high"} or (
                weather_dict.get("rainfall") or 0
            ) >= 5:
                weather_terms = " flood rain storm ရေကြီး မိုး"
            if weather_dict.get("storm"):
                weather_terms += " storm"
        osint_query = f"{question} {route_hint}{weather_terms}".strip()
        raw_hits = self.qdrant.search(osint_query or question, limit=16, recent_only=True)
        try:
            extra = self.qdrant.search_route_risk(
                osint_query or "Myanmar road logistics", limit=8
            )
        except Exception:
            extra = []
        merged: list[dict[str, Any]] = []
        seen: set[Any] = set()
        for h in [*raw_hits, *extra]:
            hid = h.get("id") or (h.get("link"), h.get("date"), (h.get("text") or "")[:40])
            if hid in seen:
                continue
            seen.add(hid)
            merged.append(h)

        osint_hits, osint_matched = select_semantic_osint(
            merged, question, weather=weather_dict, top_k=6
        )
        if not osint_matched:
            osint_hits = []

        heur = heuristic_risk(
            weather=weather_dict,
            osint_hits=osint_hits,
            shipment_status=shipment.status if shipment else None,
            gates=gates,
            position=position_dict,
            route_metrics=route_metrics,
            osint_matched=osint_matched,
        )

        context = build_context(
            question=question,
            shipment=shipment_dict,
            position=position_dict,
            weather=weather_dict,
            osint_hits=osint_hits,
            heuristic_risk=heur,
            gates=gates,
            events=events_list,
            route_metrics=route_metrics,
            osint_matched=osint_matched,
        )

        llm_out: dict[str, Any]
        try:
            system_bits = [
                "You are a Logistics Decision Agent for Myanmar trading corridors.",
                "For delivery-time / distance questions, use the MAP DISTANCE / ETA section "
                "(haversine-based) together with Weather API.",
                "Correlate Weather API with semantic Qdrant OSINT from the last 7 days when present.",
                "If no semantic OSINT, answer with Weather API + Map ETA + knowledge — do not invent OSINT.",
                "Return strict JSON only.",
            ]
            if prefer_myanmar(question):
                system_bits.append(
                    "The user question is in Myanmar. You MUST write answer, recommendation, "
                    "and reasons in Myanmar (Burmese) script. Do not reply those fields in English."
                )
            llm_out = self.llm.chat_json(
                [
                    {"role": "system", "content": " ".join(system_bits)},
                    {"role": "user", "content": context},
                ]
            )
        except Exception as exc:
            logger.exception("Gemma call failed: %s", exc)
            llm_out = {
                "answer": None,
                "risk_level": heur["risk_level"],
                "risk_score": heur["risk_score"],
                "reasons": heur["reasons"],
                "evidence": [e["detail"] for e in heur["evidence"]],
                "recommendation": heur["recommendation"],
                "_parse_failed": True,
            }

        parse_failed = bool(llm_out.get("_parse_failed"))
        if parse_failed or llm_out.get("risk_level") in (None, ""):
            risk_level = heur["risk_level"]
            risk_score = heur["risk_score"]
            reasons = list(heur["reasons"])
            if parse_failed:
                reasons = list(dict.fromkeys([*(llm_out.get("reasons") or []), *reasons]))
            evidence_raw = [e["detail"] for e in heur["evidence"]]
            recommendation = heur["recommendation"]
            answer = llm_out.get("answer")
        else:
            risk_level = str(llm_out.get("risk_level")).upper()
            try:
                risk_score = float(llm_out.get("risk_score", heur["risk_score"]))
            except (TypeError, ValueError):
                risk_score = heur["risk_score"]
            reasons = llm_out.get("reasons") or heur["reasons"]
            if isinstance(reasons, str):
                reasons = [reasons]
            evidence_raw = llm_out.get("evidence") or [e["detail"] for e in heur["evidence"]]
            if isinstance(evidence_raw, str):
                evidence_raw = [evidence_raw]
            recommendation = llm_out.get("recommendation") or heur["recommendation"]
            answer = llm_out.get("answer")

        sid = shipment.tracking_number if shipment else tracking_number or "UNKNOWN"
        fused = fuse_answer(
            weather=weather_dict,
            osint_hits=osint_hits,
            recommendation=recommendation,
            risk_level=risk_level,
            risk_score=risk_score,
            shipment_id=sid,
            route_metrics=route_metrics,
            osint_matched=osint_matched,
            question=question,
        )
        answer_str = answer if isinstance(answer, str) else (str(answer) if answer else "")
        # If user asked in Myanmar but model answered in English, prefer Myanmar fused text
        if prefer_myanmar(question) and answer_str and not prefer_myanmar(answer_str):
            answer_str = fused
        lower = answer_str.lower()
        mentions_weather = any(k in lower for k in ("weather", "rain", "flood", "မိုး", "ရေ"))
        mentions_map = any(
            k in lower for k in ("km", "eta", "hour", "map", "distance", "ကီလို", "နာရီ", "ကြာ")
        )
        mentions_osint = any(
            k in lower for k in ("osint", "qdrant", "telegram", "news", "သတင်း", "တိုက်ပွဲ")
        )
        if not answer_str or parse_failed:
            answer_str = fused
        elif route_metrics and "map distance" not in lower and not mentions_map:
            answer_str = f"{answer_str}\n\n---\n{fused}"
        elif not osint_matched:
            if not (mentions_weather or mentions_map):
                answer_str = fused
            elif "weather api" not in lower and weather_dict:
                answer_str = f"{answer_str}\n\n---\n{fused}"
        elif not (mentions_weather or mentions_osint):
            answer_str = fused
        elif not (mentions_weather and mentions_osint):
            answer_str = f"{answer_str}\n\n---\n{fused}"

        fused_evidence = [e["detail"] for e in heur["evidence"]]
        for item in evidence_raw:
            s = str(item)
            if s not in fused_evidence:
                fused_evidence.append(s)

        origin_for_zones = origin_name or (shipment.origin if shipment else "Yangon")
        dest_for_zones = dest_name or (shipment.destination if shipment else "Myawaddy")
        if osint_matched and route_metrics:
            fusion = "weather_api+map_eta+qdrant_osint_7d"
        elif route_metrics:
            fusion = "weather_api+map_eta"
        elif osint_matched:
            fusion = "weather_api+qdrant_osint_7d"
        else:
            fusion = "weather_api+llm_knowledge"

        result = {
            "shipment_id": sid,
            "intent": intent,
            "risk_level": risk_level,
            "risk_score": risk_score,
            "reasons": reasons,
            "evidence": fused_evidence,
            "evidence_structured": heur["evidence"],
            "recommendation": recommendation,
            "answer": answer_str,
            "sources": [
                {
                    "text": (h.get("text") or "")[:240],
                    "link": h.get("link"),
                    "network": h.get("network"),
                    "date": h.get("date"),
                    "category": h.get("category"),
                    "date_ts": h.get("date_ts"),
                    "score": h.get("score"),
                }
                for h in sorted(osint_hits, key=parse_hit_timestamp, reverse=True)[:6]
            ],
            "weather": weather_dict,
            "route_metrics": route_metrics,
            "osint_matched": osint_matched,
            "position": position_dict,
            "shipment": shipment_dict,
            "gates": gates,
            "events": events_list,
            "risk_zones": route_risk_zones(origin_for_zones, dest_for_zones),
            "model": self.settings.llm_model_gemma,
            "fusion": fusion,
        }

        if shipment:
            pred = LogisticsRiskPrediction(
                shipment_id=shipment.id,
                risk_score=risk_score,
                risk_level=risk_level,
                explanation=answer_str,
                model=self.settings.llm_model_gemma,
            )
            self.db.add(pred)
            self.db.commit()

        return result
