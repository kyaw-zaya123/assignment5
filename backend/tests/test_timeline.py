"""Shipment timeline + document event fields."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _sh001_id(client: TestClient, auth_headers: dict[str, str]) -> int:
    rows = client.get("/api/shipments", headers=auth_headers).json()
    for s in rows:
        if s["tracking_number"] == "SH001":
            return int(s["id"])
    raise AssertionError("SH001 missing — run python -m app.seed")


def test_timeline_shape(client: TestClient, auth_headers: dict[str, str]):
    sid = _sh001_id(client, auth_headers)
    r = client.get(f"/api/shipments/{sid}/timeline", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["tracking_number"] == "SH001"
    assert body["shipment_id"] == sid
    assert isinstance(body["steps"], list)
    assert len(body["steps"]) >= 4
    for step in body["steps"]:
        assert step["state"] in {"done", "current", "todo"}
        assert "step" in step
    assert isinstance(body["events"], list)
    assert len(body["events"]) >= 1
    ev = body["events"][0]
    for key in ("id", "event_type", "description", "timestamp"):
        assert key in ev


def test_timeline_not_found(client: TestClient, auth_headers: dict[str, str]):
    r = client.get("/api/shipments/999999/timeline", headers=auth_headers)
    assert r.status_code == 404


def test_timeline_requires_auth(client: TestClient):
    r = client.get("/api/shipments/1/timeline")
    assert r.status_code == 401


def test_driver_sees_assigned_shipments(client: TestClient, driver_headers: dict[str, str]):
    r = client.get("/api/shipments", headers=driver_headers)
    assert r.status_code == 200
    rows = r.json()
    assert any(s["tracking_number"] == "SH001" for s in rows)


def test_upload_document_attaches_timeline_event(
    client: TestClient,
    driver_headers: dict[str, str],
    auth_headers: dict[str, str],
):
    sid = _sh001_id(client, auth_headers)
    files = {"file": ("pod-test.txt", b"proof of delivery demo", "text/plain")}
    data = {"latitude": "16.75", "longitude": "98.1", "note": "pytest POD"}
    r = client.post(
        f"/api/shipments/{sid}/documents",
        headers=driver_headers,
        files=files,
        data=data,
    )
    assert r.status_code == 200, r.text
    event = r.json()["event"]
    assert event["event_type"] == "DOCUMENT"
    assert event["document_name"] == "pod-test.txt"
    assert event["document_url"]

    tl = client.get(f"/api/shipments/{sid}/timeline", headers=auth_headers).json()
    docs = [e for e in tl["events"] if e.get("document_name") == "pod-test.txt"]
    assert docs
    assert docs[-1]["document_url"]

    dl = client.get(event["document_url"], headers=driver_headers)
    assert dl.status_code == 200
    assert dl.content == b"proof of delivery demo"
