"""Real local HTTP/data/signature flow with deterministic OpenAI transport responses."""

import json
import re

import pytest
from fastapi.testclient import TestClient

from bondlayer import ai, activity
from bondlayer.ucp import server
from src.agent import main


@pytest.fixture
def clients(tmp_path, monkeypatch):
    monkeypatch.setenv("BONDLAYER_TEST_DATA", "0")
    monkeypatch.setenv("BONDLAYER_AI_MODE", "openai")
    monkeypatch.setattr(server, "UPLOADS", tmp_path)
    monkeypatch.setattr(activity, "UPLOADS", tmp_path)
    with TestClient(server.create_app()) as merchant:
        class Borrow:
            def __enter__(self): return merchant
            def __exit__(self, *args): pass
        monkeypatch.setattr(main, "_http_client", Borrow)
        with TestClient(main.app) as buyer:
            yield merchant, buyer


def test_live_mode_decodes_filters_and_saves_actual_request(clients, monkeypatch):
    merchant, buyer = clients
    calls = []
    def complete(task, instructions, data, schema):
        calls.append(task)
        meta = {"provider": "openai", "model": "test-transport", "response_id": f"test-{task}"}
        if task == "intent":
            return schema.model_validate({"clauses": [
                {"source_span": "laptop", "normalized_text": "laptop", "kind": "hard"},
                {"source_span": "at least 16GB RAM", "normalized_text": "at least 16GB RAM", "kind": "hard"},
            ]}), meta
        return schema.model_validate({"ranking": [
            {"rank": 1, "merchant": "bigram", "sku_id": "SHARED", "decisive_terms": [],
             "reasoning": "Meets the requested RAM requirement."}
        ], "recommendation": "The matching laptop is recommended from the supplied comparison."}), meta
    monkeypatch.setattr(ai, "structured", complete)
    for mid, memory, price in [("smallram", "8GB", 400), ("bigram", "16GB", 900)]:
        # Same local SKU in two stores must not collide during resolution.
        csv = f"sku,title,category,price,ram\nSHARED,Laptop {mid},laptop,{price},{memory}\n"
        assert merchant.post(f"/onboard/catalog?merchant={mid}", files={"file": ("products.csv", csv)}).status_code == 200
    response = buyer.post("/query", json={"query": "a laptop with at least 16GB RAM", "bondlayer_enabled": False})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["winner"]["merchant"] == "bigram"
    assert len(body["ranked"]) == 1
    assert calls == ["intent", "rank"]
    assert body["ai"]["intent"]["response_id"] == "test-intent"
    assert body["request_id"].startswith("live-")
    report = merchant.get(f"/onboard/requests/{body['request_id']}").json()
    assert report["source"] == "live"
    assert report["utterance"] == body["user_query"]
    assert len(merchant.get("/onboard/requests").json()) == 1
    assert report["control"] == []  # do not fabricate a comparison that was never run
    assert report["ai"]["ranking"]["response_id"] == "test-rank"
    assert next(m for m in report["merchants"] if m["won"])["fields_exposed"] > 0


def test_model_choice_with_shared_sku_reaches_checkout_and_history(clients, monkeypatch):
    merchant, buyer = clients
    def complete(task, instructions, data, schema):
        meta = {"provider": "openai", "model": "test-transport", "response_id": f"test-{task}"}
        if task == "intent":
            return schema.model_validate({"clauses": [
                {"source_span": "laptop", "normalized_text": "laptop", "kind": "hard"},
            ]}), meta
        assert task == "rank"
        offers = json.loads(re.search(r"Offers:\n(\[.*?\])\n\nRank", data, re.DOTALL).group(1))
        assert {(o["merchant"], o["sku_id"]) for o in offers} == {("cheap", "SHARED"), ("preferred", "SHARED")}
        assert "effective_cost" not in data and "credited" not in data
        return schema.model_validate({"ranking": [
            {"rank": i, "merchant": mid, "sku_id": "SHARED", "decisive_terms": [],
             "reasoning": f"Model chose {mid}"}
            for i, mid in enumerate(["preferred", "cheap"], 1)
        ], "recommendation": "The model chose the preferred store."}), meta
    monkeypatch.setattr(ai, "structured", complete)
    for mid, price in [("cheap", 400), ("preferred", 900)]:
        csv = f"sku,title,category,price\nSHARED,Laptop {mid},laptop,{price}\n"
        assert merchant.post(f"/onboard/catalog?merchant={mid}", files={"file": ("products.csv", csv)}).status_code == 200
    body = buyer.post("/query", json={"query": "a laptop", "bondlayer_enabled": False}).json()
    assert [r["merchant"] for r in body["ranked"]] == ["preferred", "cheap"]
    assert body["winner"]["reasoning"] == "Model chose preferred"
    assert body["flipped"] is True
    assert body["order"]["merchant"] == "preferred"
    assert body["order"]["order"]["status"] == "confirmed_awaiting_payment"
    report = merchant.get(f"/onboard/requests/{body['request_id']}").json()
    assert next(m for m in report["merchants"] if m["won"])["merchant"] == "preferred"
    assert "model" in next(m for m in report["merchants"] if not m["won"])["lost_because"]
    # Reset evidence between calls, including calls made on the same worker thread.
    again = buyer.post("/query", json={"query": "a laptop", "bondlayer_enabled": False}).json()
    assert len(again["transcript"]) == len(body["transcript"]) == 2


def test_live_mode_provider_failure_is_visible_without_fake_ranking(clients, monkeypatch):
    merchant, buyer = clients
    merchant.post("/onboard/catalog?merchant=own", files={"file": ("p.csv", "sku,title,category,price\n1,Laptop,laptop,999\n")})
    def fail(*args):
        raise ai.AIError("OpenAI quota or rate limit reached.", 503)
    monkeypatch.setattr(ai, "structured", fail)
    response = buyer.post("/query", json={"query": "a laptop"})
    assert response.status_code == 503
    assert "OpenAI quota" in response.json()["detail"]
    assert "ranked" not in response.json()


@pytest.mark.parametrize("rows", [[], [
    {"rank": 1, "merchant": "unknown", "sku_id": "1", "decisive_terms": [], "reasoning": "not in catalogue"},
]])
def test_unusable_model_ranking_does_not_checkout_or_save_a_fallback(clients, monkeypatch, rows):
    merchant, buyer = clients
    merchant.post("/onboard/catalog?merchant=own", files={"file": ("p.csv", "sku,title,category,price\n1,Laptop,laptop,999\n")})
    def complete(task, instructions, data, schema):
        meta = {"provider": "openai", "model": "test", "response_id": "test-response"}
        if task == "intent":
            return schema.model_validate({"clauses": [
                {"source_span": "laptop", "normalized_text": "laptop", "kind": "hard"},
            ]}), meta
        return schema.model_validate({"ranking": rows, "recommendation": "Invalid ranking"}), meta
    monkeypatch.setattr(ai, "structured", complete)
    def no_checkout(*args, **kwargs):
        pytest.fail("An unusable model ranking must not trigger checkout")
    monkeypatch.setattr(main.ucp_client, "make_checkout", no_checkout)
    response = buyer.post("/query", json={"query": "a laptop", "bondlayer_enabled": False})
    assert response.status_code == 502
    assert "known offer" in response.json()["detail"]
    assert merchant.get("/onboard/requests").json() == []
