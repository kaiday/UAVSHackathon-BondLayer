"""BONDLAYER_DEMO_DATA preloads every bundled merchant and still loads uploads."""

import pytest
from fastapi.testclient import TestClient

from bondlayer.ucp import server

SYNTHETIC = {"voltway", "citycircuit", "northgear"}
RETAILERS = {"bigw", "jb-hifi", "kmart", "officeworks"}
CSV = "sku,title,category,price,stock\nLAP-1,Work Laptop,laptop,599.00,3\n"


@pytest.fixture
def demo_app(tmp_path, monkeypatch):
    with monkeypatch.context() as patch:
        patch.delenv("BONDLAYER_TEST_DATA", raising=False)
        patch.setenv("BONDLAYER_DEMO_DATA", "1")
        patch.setattr(server, "UPLOADS", tmp_path)
        with TestClient(server.create_app()) as client:
            yield client
    server.create_app()


def test_demo_preloads_synthetic_and_retailer_merchants(demo_app):
    merchants = {m["merchant"]: m for m in demo_app.get("/onboard/merchants").json()}
    assert SYNTHETIC | RETAILERS <= set(merchants)
    assert merchants["jb-hifi"]["display_name"] == "JB Hi-Fi"
    assert merchants["officeworks"]["rows_read"] == 20
    assert demo_app.get("/health").json()["merchants"] == len(SYNTHETIC | RETAILERS)


def test_demo_keeps_signed_records_and_saved_requests(demo_app):
    profile = demo_app.get("/voltway/.well-known/ucp").json()
    assert profile["signing_keys"], "Voltway's public key must still be published"
    assert len(demo_app.get("/onboard/requests").json()) == 30


def test_retailers_are_catalogue_only(demo_app):
    body = demo_app.get("/kmart/ucp/catalog/search").json()
    assert body["products"]
    assert demo_app.get("/kmart/.well-known/ucp").json()["signing_keys"] == []


def test_uploads_still_load_alongside_demo_merchants(demo_app):
    response = demo_app.post("/onboard/catalog?merchant=my-store&create=true",
                             files={"file": ("catalogue.csv", CSV)})
    assert response.status_code == 200
    server.create_app()
    merchants = {m["merchant"] for m in demo_app.get("/onboard/merchants").json()}
    assert "my-store" in merchants and SYNTHETIC <= merchants


def test_demo_merchant_cannot_be_recreated(demo_app):
    response = demo_app.post("/onboard/catalog?merchant=voltway&create=true",
                             files={"file": ("catalogue.csv", CSV)})
    assert response.status_code == 409
