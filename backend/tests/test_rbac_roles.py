"""Role-scoped shipment / alert behaviour for ADMIN, TRADER, DRIVER."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_shipments_require_auth(client: TestClient):
    assert client.get("/api/shipments").status_code == 401


def test_alerts_require_auth(client: TestClient):
    assert client.get("/api/alerts").status_code == 401


def test_admin_sees_all_shipments(client: TestClient, auth_headers: dict):
    r = client.get("/api/shipments", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert len(r.json()) >= 1


def test_trader_only_own_shipments(client: TestClient, trader_headers: dict):
    me = client.get("/api/auth/me", headers=trader_headers).json()
    rows = client.get("/api/shipments", headers=trader_headers).json()
    assert all(s.get("trader_id") == me["id"] for s in rows)


def test_trader_create_assigns_driver(client: TestClient, trader_headers: dict, driver_headers: dict):
    created = client.post(
        "/api/shipments",
        headers=trader_headers,
        json={"origin": "Yangon", "destination": "Muse", "cargo_type": "rbac_test", "status": "CREATED"},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["trader_id"] is not None
    assert body["driver_id"] is not None

    driver_me = client.get("/api/auth/me", headers=driver_headers).json()
    assert body["driver_id"] == driver_me["id"]

    driver_rows = client.get("/api/shipments", headers=driver_headers).json()
    assert any(s["id"] == body["id"] for s in driver_rows)


def test_driver_sees_assigned_and_unassigned(client: TestClient, driver_headers: dict, auth_headers: dict):
    me = client.get("/api/auth/me", headers=driver_headers).json()
    rows = client.get("/api/shipments", headers=driver_headers).json()
    for s in rows:
        assert s.get("driver_id") in (None, me["id"])

    # Admin can still list everything
    admin_rows = client.get("/api/shipments", headers=auth_headers).json()
    assert len(admin_rows) >= len(rows)


def test_trader_cannot_patch_gate(client: TestClient, trader_headers: dict):
    gates = client.get("/api/gates").json()
    assert gates
    r = client.patch(
        f"/api/gates/{gates[0]['id']}",
        headers=trader_headers,
        json={"status": "CLOSED"},
    )
    assert r.status_code == 403


def test_trader_cannot_driver_action(client: TestClient, trader_headers: dict, driver_headers: dict):
    rows = client.get("/api/shipments", headers=driver_headers).json()
    assert rows
    sid = rows[0]["id"]
    r = client.post(
        f"/api/shipments/{sid}/driver-action",
        headers=trader_headers,
        json={"action": "start_trip", "latitude": 16.8, "longitude": 96.1},
    )
    assert r.status_code == 403
