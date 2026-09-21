"""Auth + RBAC smoke tests."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health(client: TestClient):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_login_json_success(client: TestClient):
    r = client.post(
        "/api/auth/login/json",
        json={"username": "admin", "password": "Admin123!"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == "ADMIN"
    assert body["username"] == "admin"
    assert body["access_token"]


def test_login_json_bad_password(client: TestClient):
    r = client.post(
        "/api/auth/login/json",
        json={"username": "admin", "password": "wrong"},
    )
    assert r.status_code == 401


def test_login_form_success(client: TestClient):
    r = client.post(
        "/api/auth/login",
        data={"username": "driver1", "password": "Driver123!"},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "DRIVER"


def test_me_requires_auth(client: TestClient):
    assert client.get("/api/auth/me").status_code == 401


def test_me_with_token(client: TestClient, auth_headers: dict[str, str]):
    r = client.get("/api/auth/me", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == "admin"
    assert body["role"] == "ADMIN"


def test_role_tokens(client: TestClient, trader_headers: dict, driver_headers: dict):
    t = client.get("/api/auth/me", headers=trader_headers).json()
    d = client.get("/api/auth/me", headers=driver_headers).json()
    assert t["role"] == "TRADER"
    assert d["role"] == "DRIVER"
