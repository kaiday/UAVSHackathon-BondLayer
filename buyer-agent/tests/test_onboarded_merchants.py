"""Use real merchant endpoints to test an empty installation and later uploads."""

import pytest
import httpx
from fastapi.testclient import TestClient

from bondlayer.ucp import server
from src.agent import main


@pytest.fixture
def apps(tmp_path, monkeypatch, stub_model):
    # The model decides the ranking, so these run against a stub rather than a
    # provider. It answers in the order it was given, which is run_request's, so
    # the winners these tests assert on are still the arithmetic's.
    stub_model()
    with monkeypatch.context() as patch:
        patch.delenv("BONDLAYER_TEST_DATA", raising=False)
        patch.delenv("OPENAI_API_KEY", raising=False)
        patch.setattr(server, "UPLOADS", tmp_path)
        merchant_app = server.create_app()
        patch.setattr(main, "_http_client", lambda: TestClient(merchant_app))
        with TestClient(merchant_app) as merchant, TestClient(main.app) as buyer:
            yield merchant, buyer
    server.create_app()


def test_empty_registry_has_no_winner_and_requests_onboarding(apps):
    merchant, buyer = apps
    assert merchant.get("/onboard/merchants").json() == []
    response = buyer.post("/query", json={"query": "a laptop"})
    assert response.status_code == 200
    body = response.json()
    assert body["onboarding_required"] is True
    assert body["winner"] is None and body["ranked"] == []
    assert body["order"]["order"] is None


def test_new_merchant_is_discovered_without_restarting_agent(apps):
    merchant, buyer = apps
    assert buyer.post("/query", json={"query": "a laptop"}).json()["winner"] is None
    response = merchant.post("/onboard/catalog?merchant=retailer", files={"file": (
        "products.csv", "sku,title,category,price,stock\nOWN-1,My Laptop,laptop,599,2\n")})
    assert response.status_code == 200
    for enabled in (False, True):
        response = buyer.post("/query", json={"query": "a laptop under $700", "bondlayer_enabled": enabled})
        assert response.status_code == 200
        body = response.json()
        assert body["onboarding_required"] is False
        assert body["winner"]["merchant"] == "retailer"
        assert body["winner"]["credited_aud"] == "0"
        assert body["order"]["order"]["line_items"][0]["sku_id"] == "OWN-1"
        assert {r["merchant"] for r in body["ranked"]} == {"retailer"}


def test_uploaded_catalogue_beyond_one_page_is_fully_searched(apps):
    merchant, buyer = apps
    rows = [f"SKU-{i},Laptop {i},laptop,{1000 if i < 100 else 500}" for i in range(101)]
    content = "sku,title,category,price\n" + "\n".join(rows)
    assert merchant.post("/onboard/catalog?merchant=retailer", files={"file": ("products.csv", content)}).status_code == 200
    body = buyer.post("/query", json={"query": "a laptop"}).json()
    assert len(body["ranked"]) == 101
    assert body["winner"]["sku_id"] == "SKU-100"


@pytest.mark.parametrize("query", ["", "   "])
def test_blank_query_is_a_validation_error(apps, query):
    assert apps[1].post("/query", json={"query": query}).status_code == 422


def test_unavailable_registry_returns_actionable_503(monkeypatch):
    def fail():
        raise httpx.ConnectError("offline")
    monkeypatch.setattr(main, "_http_client", fail)
    response = TestClient(main.app).post("/query", json={"query": "a laptop"})
    assert response.status_code == 503
    assert "Merchant service is unavailable" in response.json()["detail"]
