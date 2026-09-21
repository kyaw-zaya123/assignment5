"""Shared fixtures — TestClient against seeded PostGIS."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


def _login(client: TestClient, username: str, password: str) -> dict:
    r = client.post("/api/auth/login/json", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="session")
def admin_token(client: TestClient) -> str:
    return _login(client, "admin", "Admin123!")["access_token"]


@pytest.fixture(scope="session")
def trader_token(client: TestClient) -> str:
    return _login(client, "trader", "Trader123!")["access_token"]


@pytest.fixture(scope="session")
def driver_token(client: TestClient) -> str:
    return _login(client, "driver1", "Driver123!")["access_token"]


@pytest.fixture
def auth_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def trader_headers(trader_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {trader_token}"}


@pytest.fixture
def driver_headers(driver_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {driver_token}"}
