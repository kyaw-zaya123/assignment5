"""Border gate list / impact / ADMIN update tests."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def _myawaddy_id(client: TestClient) -> int:
    gates = client.get("/api/gates").json()
    for g in gates:
        if g["name"] == "Myawaddy":
            return int(g["id"])
    raise AssertionError("Myawaddy gate missing — run python -m app.seed")


def test_list_gates(client: TestClient):
    r = client.get("/api/gates")
    assert r.status_code == 200
    gates = r.json()
    assert isinstance(gates, list)
    assert len(gates) >= 1
    names = {g["name"] for g in gates}
    assert "Myawaddy" in names
    for g in gates:
        assert g["status"] in {"OPEN", "WARNING", "CLOSED"}


def test_gate_impact_requires_auth(client: TestClient):
    gid = _myawaddy_id(client)
    assert client.get(f"/api/gates/{gid}/impact").status_code == 401


def test_gate_impact(client: TestClient, auth_headers: dict[str, str]):
    gid = _myawaddy_id(client)
    r = client.get(f"/api/gates/{gid}/impact", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["gate"]["name"] == "Myawaddy"
    assert isinstance(body.get("affected_shipments"), list)
    assert any(s["tracking_number"] == "SH001" for s in body["affected_shipments"])


def test_patch_gate_forbidden_for_trader(client: TestClient, trader_headers: dict[str, str]):
    gid = _myawaddy_id(client)
    r = client.patch(
        f"/api/gates/{gid}",
        headers=trader_headers,
        json={"status": "OPEN"},
    )
    assert r.status_code == 403


def test_patch_gate_open_no_ai(client: TestClient, auth_headers: dict[str, str]):
    """OPEN path creates alerts but skips LogisticsAgent."""
    gid = _myawaddy_id(client)
    r = client.patch(
        f"/api/gates/{gid}",
        headers=auth_headers,
        json={"status": "OPEN"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["new_status"] == "OPEN"
    assert body["gate"]["status"] == "OPEN"
    assert body["ai_ran"] is False
    assert "summary" in body


def test_patch_gate_closed_with_mocked_ai(client: TestClient, auth_headers: dict[str, str]):
    gid = _myawaddy_id(client)
    fake = {
        "risk_level": "HIGH",
        "risk_score": 0.9,
        "recommendation": "Hold at checkpoint",
        "evidence": ["gate closed"],
        "evidence_structured": [{"source": "gate", "detail": "CLOSED"}],
        "answer": "High risk due to closed gate",
    }
    try:
        with patch(
            "app.api.routes.gates.LogisticsAgent.assess",
            return_value=fake,
        ):
            r = client.patch(
                f"/api/gates/{gid}",
                headers=auth_headers,
                json={"status": "CLOSED"},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["new_status"] == "CLOSED"
        assert body["ai_ran"] is True
        assert body["affected_count"] >= 1
        hit = next(
            (s for s in body["affected_shipments"] if s["tracking_number"] == "SH001"),
            None,
        )
        assert hit is not None
        assert hit["risk_level"] == "HIGH"
        assert hit["recommendation"] == "Hold at checkpoint"
    finally:
        # restore demo default
        client.patch(
            f"/api/gates/{gid}",
            headers=auth_headers,
            json={"status": "OPEN"},
        )


def test_patch_gate_not_found(client: TestClient, auth_headers: dict[str, str]):
    r = client.patch(
        "/api/gates/999999",
        headers=auth_headers,
        json={"status": "OPEN"},
    )
    assert r.status_code == 404
