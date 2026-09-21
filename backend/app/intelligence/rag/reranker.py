"""Rerank OSINT + select semantic matches (last-7-day hits from Qdrant)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from app.intelligence.rag.embeddings import extract_keywords

RISK_TERMS = (
    "flood",
    "road",
    "closure",
    "block",
    "conflict",
    "clash",
    "landslide",
    "checkpoint",
    "rain",
    "storm",
    "highway",
    "bridge",
    "ကားလမ်း",
    "ရေကြီး",
    "တိုက်ပွဲ",
    "နယ်စပ်",
)


def parse_hit_timestamp(hit: dict[str, Any]) -> float:
    """Return unix seconds for ranking (0 if unknown)."""
    ts = hit.get("date_ts")
    if ts is not None:
        try:
            return float(ts)
        except (TypeError, ValueError):
            pass
    raw = hit.get("date")
    if not raw:
        return 0.0
    text = str(raw).strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d",
        "%d/%m/%Y",
    ):
        try:
            return datetime.strptime(text[:19], fmt).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    return 0.0


def date_recency_bonus(ts: float, *, half_life_days: float = 7.0) -> float:
    """Prefer newer docs within the 7-day OSINT window."""
    if ts <= 0:
        return 0.02
    now = datetime.now(timezone.utc).timestamp()
    age_days = max(0.0, (now - ts) / 86400.0)
    return 0.45 * (0.5 ** (age_days / half_life_days))


def weather_alignment_bonus(hit: dict[str, Any], weather: dict[str, Any] | None) -> float:
    if not weather:
        return 0.0
    text = str(hit.get("text") or "").lower()
    bonus = 0.0
    rain = float(weather.get("rainfall") or 0)
    flood = str(weather.get("flood_risk") or "").lower()
    if rain >= 5 or flood in {"medium", "high"} or weather.get("storm"):
        for term in ("rain", "flood", "storm", "ရေကြီး", "မိုး", "ရေလွှမ်း"):
            if term in text:
                bonus += 0.08
    return min(0.25, bonus)


def query_terms(query: str) -> list[str]:
    """Terms for overlap checks — keywords + Latin words + Myanmar runs (no alias table)."""
    terms: list[str] = []
    try:
        terms.extend(extract_keywords(query) or [])
    except Exception:
        pass
    terms.extend(re.findall(r"[A-Za-z][A-Za-z'-]{2,}", query or ""))
    terms.extend(re.findall(r"[\u1000-\u109F\uAA60-\uAA7F]{2,}", query or ""))
    out: list[str] = []
    seen: set[str] = set()
    for t in terms:
        k = t.lower().strip()
        if len(k) < 2 or k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out


def rerank(
    hits: list[dict[str, Any]],
    query: str,
    top_k: int = 6,
    weather: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    q = query.lower()
    scored: list[tuple[float, dict[str, Any]]] = []
    for h in hits:
        text = str(h.get("text") or "")
        base = float(h.get("score") or 0.0)
        bonus = 0.0
        for term in RISK_TERMS:
            if re.search(re.escape(term), text, re.I) or term.lower() in q:
                bonus += 0.05
        ts = parse_hit_timestamp(h)
        h = {**h, "date_ts": ts or h.get("date_ts")}
        bonus += date_recency_bonus(ts)
        bonus += weather_alignment_bonus(h, weather)
        # query-term overlap bonus (semantic-ish without embeddings)
        blob = text.lower()
        overlap = sum(1 for t in query_terms(query) if t in blob)
        bonus += min(0.35, 0.08 * overlap)
        scored.append((base + bonus, {**h, "_overlap": overlap, "_rank": base + bonus}))
    scored.sort(key=lambda x: (x[0], parse_hit_timestamp(x[1])), reverse=True)
    out = [h for _, h in scored[:top_k]]
    out.sort(key=parse_hit_timestamp, reverse=True)
    return out


def select_semantic_osint(
    hits: list[dict[str, Any]],
    query: str,
    *,
    weather: dict[str, Any] | None = None,
    min_vector_score: float = 0.22,
    min_overlap: int = 1,
    top_k: int = 6,
) -> tuple[list[dict[str, Any]], bool]:
    """
    Keep only hits that look semantically related to the question.
    Returns (hits, matched). Empty → caller should answer with Weather API only.
    """
    if not hits:
        return [], False
    ranked = rerank(hits, query, top_k=max(top_k * 2, top_k), weather=weather)
    terms = query_terms(query)
    selected: list[dict[str, Any]] = []
    for h in ranked:
        score = h.get("score")
        overlap = int(h.get("_overlap") or 0)
        vector_ok = score is not None and float(score) >= min_vector_score
        overlap_ok = overlap >= min_overlap and bool(terms)
        if vector_ok or overlap_ok:
            selected.append(h)
    selected = selected[:top_k]
    return selected, bool(selected)
