"""Fuse Weather API + Map haversine ETA + last-7-day Qdrant OSINT for the LLM."""

from __future__ import annotations

import re
from typing import Any

from app.intelligence.rag.reranker import parse_hit_timestamp


def prefer_myanmar(text: str) -> bool:
    """True when the user question is primarily Myanmar script."""
    raw = text or ""
    my = len(re.findall(r"[\u1000-\u109F\uAA60-\uAA7F]", raw))
    latin = len(re.findall(r"[A-Za-z]", raw))
    return my >= 8 or (my > 0 and my >= latin)


def build_context(
    *,
    question: str,
    shipment: dict[str, Any] | None,
    position: dict[str, Any] | None,
    weather: dict[str, Any] | None,
    osint_hits: list[dict[str, Any]],
    heuristic_risk: dict[str, Any],
    gates: list[dict[str, Any]] | None = None,
    events: list[dict[str, Any]] | None = None,
    route_metrics: dict[str, Any] | None = None,
    osint_matched: bool = True,
) -> str:
    hits = sorted(osint_hits, key=parse_hit_timestamp, reverse=True)
    myanmar = prefer_myanmar(question)

    lines = [
        "You are a Myanmar logistics decision agent.",
        "Combine sources as follows:",
        "  (1) Live Weather API facts.",
        "  (2) MAP DISTANCE / ETA from coordinates (haversine × road factor, weather-adjusted) when present — "
        "prefer this for delivery-time questions.",
        "  (3) Qdrant OSINT from the LAST 7 DAYS only, when semantic hits are present.",
        "  (4) Your logistics knowledge only to fill gaps — mark as knowledge, not OSINT.",
        "If Qdrant has NO semantic matches: use Weather API + Map ETA (when present) + knowledge. "
        "Do NOT invent OSINT. Never cite news older than 7 days.",
    ]
    if myanmar:
        lines.extend(
            [
                "LANGUAGE (mandatory): The user asked in Myanmar (Burmese).",
                "Write `answer`, `recommendation`, `reasons`, and narrative `evidence` strings "
                "in natural Myanmar script. Keep place names, tracking IDs, numbers, and "
                "risk_level (LOW|MEDIUM|HIGH) as-is. Do not answer the narrative in English.",
            ]
        )
    else:
        lines.append(
            "LANGUAGE: Match the user question language (English if the question is English)."
        )
    lines.extend(
        [
            f"User question: {question}",
            "",
            "=== SHIPMENT ===",
        ]
    )
    if shipment:
        lines.extend(
            [
                f"tracking_number: {shipment.get('tracking_number')}",
                f"status: {shipment.get('status')}",
                f"origin: {shipment.get('origin')} -> destination: {shipment.get('destination')}",
                f"cargo: {shipment.get('cargo_type')} weight={shipment.get('weight')}",
            ]
        )
    else:
        lines.append("(no shipment bound — interpret places from the user question)")

    lines.append("")
    lines.append("=== GPS ===")
    if position:
        lines.append(
            f"lat={position.get('latitude')} lon={position.get('longitude')} "
            f"speed={position.get('speed')} at={position.get('timestamp')}"
        )
    else:
        lines.append("(no live GPS)")

    lines.append("")
    lines.append("=== WEATHER API (live) ===")
    if weather:
        lines.append(
            f"condition={weather.get('condition')} rain={weather.get('rainfall')} mm "
            f"storm={weather.get('storm')} flood_risk={weather.get('flood_risk')} "
            f"temp={weather.get('temperature')} humidity={weather.get('humidity')} "
            f"provider={weather.get('provider')}"
        )
    else:
        lines.append("(weather unavailable)")

    lines.append("")
    lines.append("=== MAP DISTANCE / ETA (haversine × 1.35 road factor) ===")
    if route_metrics:
        lines.append(
            f"route: {route_metrics.get('origin')} → {route_metrics.get('destination')}"
        )
        lines.append(
            f"straight_km={route_metrics.get('straight_km')} "
            f"road_km≈{route_metrics.get('road_km')} "
            f"assumed_speed_kmh={route_metrics.get('assumed_speed_kmh')}"
        )
        lines.append(
            f"eta: {route_metrics.get('eta_text')} "
            f"(low={route_metrics.get('eta_hours_low')}h high={route_metrics.get('eta_hours_high')}h)"
        )
        lines.append(f"weather_adjustment: {route_metrics.get('weather_note')}")
        lines.append(f"source: {route_metrics.get('source')}")
    else:
        lines.append("(route coords unavailable — use knowledge for ETA if asked)")

    lines.append("")
    lines.append("=== BORDER GATES ===")
    if gates:
        for g in gates:
            lines.append(f"- {g.get('name')}: {g.get('status')} ({g.get('location')})")
    else:
        lines.append("(no gate data)")

    lines.append("")
    lines.append("=== TIMELINE EVENTS ===")
    if events:
        for e in events[:8]:
            lines.append(
                f"- {e.get('event_type')}: {e.get('description')} @ {e.get('location')}"
            )
    else:
        lines.append("(no events)")

    lines.append("")
    lines.append("=== QDRANT OSINT (semantic matches, last 7 days, newest first) ===")
    if not hits or not osint_matched:
        lines.append(
            "(no semantic OSINT in the last 7 days — "
            "FALLBACK: Weather API + Map ETA + knowledge; do NOT cite OSINT)"
        )
    for i, hit in enumerate(hits[:8], 1):
        text = (hit.get("text") or "").replace("\n", " ")[:320]
        lines.append(
            f"[{i}] score={hit.get('score')} date={hit.get('date')} "
            f"network={hit.get('network')} category={hit.get('category')} "
            f"link={hit.get('link')}"
        )
        lines.append(f"    {text}")

    lines.append("")
    lines.append("=== FUSION HINT ===")
    if route_metrics and weather:
        lines.append(
            "Lead delivery-time answers with Map ETA, then Weather API, then OSINT if matched: "
            f"eta={route_metrics.get('eta_text')}, road_km≈{route_metrics.get('road_km')}, "
            f"weather={weather.get('condition')}/{weather.get('rainfall')}mm."
        )
    elif weather and hits and osint_matched:
        lines.append("Combine Weather API with newest semantic OSINT.")
    elif weather:
        lines.append("Weather + knowledge only (no map coords / no OSINT).")
    else:
        lines.append("Limited evidence — say so clearly.")

    lines.append("")
    lines.append("=== HEURISTIC RISK ===")
    lines.append(
        f"score={heuristic_risk.get('risk_score')} level={heuristic_risk.get('risk_level')} "
        f"reasons={heuristic_risk.get('reasons')}"
    )
    lines.append("")
    if myanmar:
        lines.append(
            "Respond with STRICT JSON only (no markdown). "
            "Fields answer/recommendation/reasons must be Myanmar language. "
            'Example shape: {"shipment_id":"...","risk_level":"LOW|MEDIUM|HIGH","risk_score":0.0,'
            '"evidence":["မြေပုံ: ...","မိုးလေဝသ: ..."],'
            '"reasons":["..."],"recommendation":"...","answer":"..."}'
        )
    else:
        lines.append(
            "Respond with STRICT JSON only (no markdown): "
            '{"shipment_id":"...","risk_level":"LOW|MEDIUM|HIGH","risk_score":0.0,'
            '"evidence":["Map: ...","Weather API: ..."],'
            '"reasons":["..."],"recommendation":"...","answer":"..."}'
        )
    return "\n".join(lines)


def fuse_answer(
    *,
    weather: dict[str, Any] | None,
    osint_hits: list[dict[str, Any]],
    recommendation: str,
    risk_level: str,
    risk_score: float,
    shipment_id: str | None = None,
    route_metrics: dict[str, Any] | None = None,
    osint_matched: bool = True,
    question: str | None = None,
) -> str:
    """Deterministic fallback — Map ETA + Weather + optional semantic OSINT."""
    myanmar = prefer_myanmar(question or "")
    parts: list[str] = []

    if myanmar:
        if shipment_id:
            parts.append(f"ပို့ဆောင်မှု {shipment_id}: အန္တရာယ် {risk_level} ({risk_score})။")
        else:
            parts.append(f"အန္တရာယ် {risk_level} ({risk_score})။")

        if route_metrics:
            parts.append(
                "မြေပုံအကွာအဝေး: "
                f"{route_metrics.get('origin')} → {route_metrics.get('destination')}, "
                f"လမ်းခရီး ≈{route_metrics.get('road_km')} ကီလိုမီတာ "
                f"(မျဉ်းဖြောင့် {route_metrics.get('straight_km')} ကီလိုမီတာ)။ "
                f"ခန့်မှန်းပို့ချိန် {route_metrics.get('eta_text')} "
                f"(≈{route_metrics.get('assumed_speed_kmh')} km/h၊ "
                f"{route_metrics.get('weather_note')})။"
            )

        if weather:
            parts.append(
                "မိုးလေဝသ API: "
                f"အခြေအနေ={weather.get('condition')}, မိုး={weather.get('rainfall')} mm, "
                f"ရေကြီးအန္တရာယ်={weather.get('flood_risk')}, "
                f"အပူချိန်={weather.get('temperature')}°C။"
            )
        else:
            parts.append("မိုးလေဝသ API: မရရှိပါ။")

        hits = sorted(osint_hits, key=parse_hit_timestamp, reverse=True) if osint_matched else []
        if hits:
            parts.append("နောက်ဆုံး ၇ ရက်အတွင်း သက်ဆိုင်သော OSINT:")
            for h in hits[:3]:
                snippet = (h.get("text") or "").replace("\n", " ").strip()[:160]
                parts.append(
                    f"- [{h.get('date') or 'ရက်စွဲမရှိ'}] {h.get('network') or 'OSINT'}: {snippet}"
                )
        else:
            parts.append(
                "Qdrant OSINT: လွန်ခဲ့သော ၇ ရက်အတွင်း သက်ဆိုင်သော အချက်အလက် မတွေ့ပါ — "
                "မိုးလေဝသ API + မြေပုံအကွာအဝေး/ပို့ချိန် + ယာဉ်လမ်းအသိပညာဖြင့် ဖြေထားသည်။"
            )

        parts.append(f"အကြံပြုချက်: {recommendation}")
        return "\n".join(parts)

    if shipment_id:
        parts.append(f"Shipment {shipment_id}: risk {risk_level} ({risk_score}).")
    else:
        parts.append(f"Risk {risk_level} ({risk_score}).")

    if route_metrics:
        parts.append(
            "Map distance: "
            f"{route_metrics.get('origin')} → {route_metrics.get('destination')}, "
            f"≈{route_metrics.get('road_km')} km road "
            f"(straight {route_metrics.get('straight_km')} km). "
            f"Estimated delivery time {route_metrics.get('eta_text')} "
            f"at ~{route_metrics.get('assumed_speed_kmh')} km/h "
            f"({route_metrics.get('weather_note')})."
        )

    if weather:
        parts.append(
            "Weather API: "
            f"condition={weather.get('condition')}, rain={weather.get('rainfall')} mm, "
            f"flood_risk={weather.get('flood_risk')}, temp={weather.get('temperature')}°C."
        )
    else:
        parts.append("Weather API: unavailable.")

    hits = sorted(osint_hits, key=parse_hit_timestamp, reverse=True) if osint_matched else []
    if hits:
        parts.append("Latest semantic Qdrant OSINT (last 7 days):")
        for h in hits[:3]:
            snippet = (h.get("text") or "").replace("\n", " ").strip()[:160]
            parts.append(
                f"- [{h.get('date') or 'unknown date'}] {h.get('network') or 'OSINT'}: {snippet}"
            )
    else:
        parts.append(
            "Qdrant OSINT: no semantic matches in the last 7 days — "
            "answer based on Weather API + map distance/ETA + logistics knowledge."
        )

    parts.append(f"Recommendation: {recommendation}")
    return "\n".join(parts)
