"""Reports cross an authenticated HTTP boundary instead of sharing agent disk."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from bondlayer import activity
from bondlayer.ucp import server


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("BONDLAYER_TEST_DATA", "0")
    monkeypatch.setenv("BONDLAYER_SERVICE_TOKEN", "test-shared-token")
    monkeypatch.setenv("BONDLAYER_REQUIRE_SERVICE_TOKEN", "1")
    monkeypatch.setattr(server, "UPLOADS", tmp_path)
    monkeypatch.setattr(activity, "UPLOADS", tmp_path)
    with TestClient(server.create_app()) as client:
        assert client.post("/onboard/catalog?merchant=shop", files={"file": (
            "catalogue.csv", "sku,title,category,price\n1,My laptop,laptop,999\n",
        )}).status_code == 200
        yield client


def report():
    return {
        "request_id": f"live-{uuid4().hex}", "source": "live",
        "created_at": datetime.now(timezone.utc).isoformat(), "utterance": "a laptop",
        "merchants": [{"merchant": "shop", "won": True, "control_merchant": False}],
        "constraints": [], "control": [], "extension_enabled": True,
    }


AUTH = {"X-BondLayer-Service-Token": "test-shared-token"}


def test_authenticated_report_is_visible_and_survives_restart(client):
    payload = report()
    assert client.post("/internal/requests", json=payload).status_code == 401
    assert client.get("/onboard/requests").json() == []
    response = client.post("/internal/requests", json=payload, headers=AUTH)
    assert response.json() == {"request_id": payload["request_id"], "saved": True}
    assert client.post("/internal/requests", json=payload, headers=AUTH).status_code == 200
    assert len(client.get("/onboard/requests").json()) == 1
    with TestClient(server.create_app()) as restarted:
        saved = restarted.get(f"/onboard/requests/{payload['request_id']}")
        assert saved.status_code == 200
        assert saved.json()["utterance"] == "a laptop"


def test_report_ids_cannot_escape_storage_or_overwrite_other_events(client):
    payload = report()
    assert client.post("/internal/requests", json=payload, headers=AUTH).status_code == 200
    payload["utterance"] = "changed report"
    assert client.post("/internal/requests", json=payload, headers=AUTH).status_code == 409
    payload["request_id"] = "../../outside"
    assert client.post("/internal/requests", json=payload, headers=AUTH).status_code == 422


def test_unknown_merchants_and_oversize_reports_are_refused(client):
    payload = report()
    payload["merchants"][0]["merchant"] = "unknown"
    assert client.post("/internal/requests", json=payload, headers=AUTH).status_code == 422
    assert client.post("/internal/requests", content=b"x" * (2 * 1024 * 1024 + 1), headers=AUTH).status_code == 413


def test_cloud_requires_token_but_local_loopback_can_run_without_one(client, monkeypatch):
    monkeypatch.delenv("BONDLAYER_SERVICE_TOKEN")
    assert client.post("/internal/requests", json=report()).status_code == 503
    monkeypatch.delenv("BONDLAYER_REQUIRE_SERVICE_TOKEN")
    monkeypatch.delenv("FLY_APP_NAME", raising=False)
    with TestClient(server.create_app(), client=("127.0.0.1", 50000)) as local:
        assert local.post("/internal/requests", json=report()).status_code == 200
    assert client.post("/internal/requests", json=report()).status_code == 503
