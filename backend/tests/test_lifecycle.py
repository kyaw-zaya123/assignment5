"""Shipment lifecycle: reject status skips (e.g. CREATED → delivered)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _create_shipment(client: TestClient, trader_headers: dict) -> int:
    r = client.post(
        "/api/shipments",
        headers=trader_headers,
        json={
            "origin": "Yangon",
            "destination": "Myawaddy",
            "cargo_type": "lifecycle_test",
            "status": "CREATED",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_cannot_deliver_from_created(client: TestClient, trader_headers: dict, driver_headers: dict):
    sid = _create_shipment(client, trader_headers)
    r = client.post(
        f"/api/shipments/{sid}/driver-action",
        headers=driver_headers,
        json={"action": "delivered", "latitude": 16.8, "longitude": 96.1},
    )
    assert r.status_code == 409
    assert "Cannot" in r.json()["detail"]


def test_cannot_skip_to_customs(client: TestClient, trader_headers: dict, driver_headers: dict):
    sid = _create_shipment(client, trader_headers)
    r = client.post(
        f"/api/shipments/{sid}/driver-action",
        headers=driver_headers,
        json={"action": "customs_completed", "latitude": 16.8, "longitude": 96.1},
    )
    assert r.status_code == 409


def test_happy_path_lifecycle(client: TestClient, trader_headers: dict, driver_headers: dict):
    sid = _create_shipment(client, trader_headers)
    steps = [
        ("start_trip", "IN_TRANSIT"),
        ("arrived_checkpoint", "CHECKPOINT"),
        ("customs_completed", "CUSTOMS"),
        ("delivered", "DELIVERED"),
    ]
    for action, expect in steps:
        r = client.post(
            f"/api/shipments/{sid}/driver-action",
            headers=driver_headers,
            json={"action": action, "latitude": 16.8, "longitude": 96.2},
        )
        assert r.status_code == 200, (action, r.text)
        assert r.json()["shipment"]["status"] == expect

    # No further trip advance
    r = client.post(
        f"/api/shipments/{sid}/driver-action",
        headers=driver_headers,
        json={"action": "start_trip", "latitude": 16.8, "longitude": 96.2},
    )
    assert r.status_code == 409


def test_gps_allowed_without_advancing(client: TestClient, trader_headers: dict, driver_headers: dict):
    sid = _create_shipment(client, trader_headers)
    r = client.post(
        f"/api/shipments/{sid}/driver-action",
        headers=driver_headers,
        json={"action": "update_location", "latitude": 16.85, "longitude": 96.15},
    )
    assert r.status_code == 200
    assert r.json()["shipment"]["status"] == "CREATED"
