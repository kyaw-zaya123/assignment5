"""Map ETA + semantic OSINT selection tests."""

from __future__ import annotations

from app.gis.eta import estimate_route_metrics, find_places_in_text, resolve_map_corridor
from app.gis.spatial import haversine_km
from app.intelligence.rag.reranker import select_semantic_osint


def test_haversine_meiktila_muse():
    km = haversine_km(20.8778, 95.8583, 23.9780, 97.9040)
    assert 300 < km < 600


def test_find_english_places(client):
    from app.database.postgres import SessionLocal

    db = SessionLocal()
    try:
        places = find_places_in_text(db, "How long from Taungoo to Muse?")
        assert places[:2] == ["Taungoo", "Muse"]
    finally:
        db.close()


def test_map_corridor_prefers_question_english(client):
    from app.database.postgres import SessionLocal

    db = SessionLocal()
    try:
        o, d = resolve_map_corridor(
            db,
            "Taungoo-Muse delivery ETA?",
            shipment_origin="Sittwe",
            shipment_dest="Yangon Port",
        )
        assert o == "Taungoo"
        assert d == "Muse"
        m = estimate_route_metrics(db, o, d, weather={"condition": "clouds", "rainfall": 0})
        assert m is not None
        assert m["road_km"] > 500
        assert "hours" in m["eta_text"] or "days" in m["eta_text"]
    finally:
        db.close()


def test_map_falls_back_to_shipment_when_no_places(client):
    from app.database.postgres import SessionLocal

    db = SessionLocal()
    try:
        o, d = resolve_map_corridor(
            db,
            "ပို့ချိန်ဘယ်လောက်ကြာမလဲ",
            shipment_origin="Yangon",
            shipment_dest="Myawaddy",
        )
        assert o == "Yangon"
        assert d == "Myawaddy"
        m = estimate_route_metrics(db, o, d)
        assert m is not None
        assert m["origin"] == "Yangon"
    finally:
        db.close()


def test_semantic_empty_unrelated():
    hits = [
        {"text": "Nepal flood stations", "score": 0.05, "date": "2026-09-15"},
    ]
    selected, ok = select_semantic_osint(hits, "Taungoo to Muse delivery time")
    assert ok is False
    assert selected == []
