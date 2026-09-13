"""Network-free contract tests; live OpenAI is checked separately with real credentials."""

import pytest
from fastapi.testclient import TestClient

from bondlayer import ai, activity
from bondlayer.ucp import server
from bondlayer.ucp.capabilities import BENEFIT_VALUE, CATALOG_SEARCH, CHECKOUT
from bondlayer.ucp.intent import verified_records

POLICY = "All laptops include free return shipping and a 60-day return window. Keep the original packaging."
CSV = "sku,title,category,price,stock\nSKU-1,Own laptop,laptop,999,3\n"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("BONDLAYER_TEST_DATA", "0")
    monkeypatch.setenv("BONDLAYER_AI_MODE", "openai")
    monkeypatch.setattr(server, "UPLOADS", tmp_path)
    monkeypatch.setattr(activity, "UPLOADS", tmp_path)
    with TestClient(server.create_app()) as client:
        response = client.post("/onboard/catalog?merchant=ownstore", data={"domain": "ownstore.example"}, files={"file": ("products.csv", CSV)})
        assert response.status_code == 200
        yield client


def extraction(task, instructions, data, schema):
    assert task == "policy_extraction"
    return schema.model_validate({"benefits": [{
        "benefit_type": "free_returns", "source_passages": [0],
        "section": "Returns", "facts": [{"key": "days", "value": 60}, {"key": "scope", "value": "laptop"}],
        "categories": ["laptop"], "conditions": ["Keep the original packaging."], "sku_id": None, "expires_at": None,
    }]}), {"provider": "openai", "model": "test-transport", "response_id": "test-policy"}


def test_policy_approval_publishes_real_signatures_and_survives_restart(client, monkeypatch):
    monkeypatch.setattr(ai, "structured", extraction)
    result = client.post("/onboard/policies/ownstore", files={"file": ("terms.txt", POLICY)})
    assert result.status_code == 200, result.text
    draft = result.json()["drafts"][0]
    assert draft["status"] == "pending"
    assert POLICY in draft["record"]["conditions"]
    assert "confidence" not in draft
    assert client.post("/onboard/policies/ownstore/publish").json()["published"] == 0
    assert verified_records(server._merchants["ownstore"]) == []
    path = f"/onboard/policies/ownstore/drafts/{draft['draft_id']}"
    assert client.patch(path, json={"value_ceiling_aud": "40.00"}).status_code == 200
    assert client.post(path + "/approve").status_code == 200
    assert client.post("/onboard/policies/ownstore/publish").json()["published"] == 1
    headers = {"UCP-Agent": f"{CATALOG_SEARCH};{BENEFIT_VALUE};{CHECKOUT}"}
    assert client.get("/ownstore/ucp/catalog/search", headers=headers).json()["extensions"][BENEFIT_VALUE]
    from bondlayer.agent import run_request
    from bondlayer.records.serialise import signed_from_json
    from bondlayer.ucp.intent import verifiers_for
    from bondlayer.types import Constraint, ConstraintKind
    verifier = verifiers_for(server._merchants["ownstore"])[0]
    run = run_request(
        "return easily", ["ownstore"],
        lambda *args, **kwargs: client.get("/ownstore/ucp/catalog/search", headers=headers).json(),
        interpret=lambda _: [Constraint("return easily", ConstraintKind.SERVICE)],
        verify=lambda entry: verifier.verify(signed_from_json(entry)),
        merchant_domains={"ownstore": "ownstore.example"},
    )
    assert run.winner.resolved[0].satisfied
    assert run.winner.resolved[0].evidence_record_id == draft["draft_id"]
    receipt = client.post("/ownstore/ucp/checkout", headers=headers, json={"items": [{"sku_id": "SKU-1", "quantity": 1}], "cited_record_ids": [draft["draft_id"]]}).json()
    assert receipt["honoured_benefits"][0]["honoured"] is True
    assert receipt["order"]["payment"]["status"] == "out_of_scope"
    assert client.post("/onboard/catalog?merchant=ownstore", files={"file": ("products.csv", CSV)}).status_code == 200
    assert verified_records(server._merchants["ownstore"])
    server.seed()
    assert len(verified_records(server._merchants["ownstore"])) == 1
    public = client.get("/ownstore/.well-known/ucp").json()["signing_keys"][0]
    assert "d" not in public


def test_model_failure_and_unquoted_claim_cannot_replace_existing_drafts(client, monkeypatch):
    monkeypatch.setattr(ai, "structured", extraction)
    uploaded = client.post("/onboard/policies/ownstore", files={"file": ("terms.txt", POLICY)}).json()
    original_id = uploaded["drafts"][0]["draft_id"]

    def invented(*args):
        result, meta = extraction(*args)
        result.benefits[0].source_passages = [99999]
        return result, meta

    monkeypatch.setattr(ai, "structured", invented)
    assert client.post("/onboard/policies/ownstore", files={"file": ("terms.txt", POLICY)}).status_code == 502
    assert client.get("/onboard/policies/ownstore").json()["drafts"][0]["draft_id"] == original_id


def test_missing_key_is_an_error_not_a_canned_answer(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.post("/onboard/ask/ownstore", json={"question": "What should I improve?"})
    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]
    assert "answer" not in response.json()


def test_unknown_ai_citations_are_rejected(client, monkeypatch):
    def bad_citation(task, instructions, data, schema):
        return schema(answer="Invented citation", diagnostic_ids=[99999]), {}
    monkeypatch.setattr(ai, "structured", bad_citation)
    assert client.post("/onboard/ask/ownstore", json={"question": "What should I improve?"}).status_code == 502


def test_merchant_profiles_are_saved_and_signing_identity_is_protected(client):
    response = client.patch("/onboard/merchants/ownstore", json={"display_name": "Renamed store", "domain": "ownstore.example"})
    assert response.status_code == 200
    server.seed()
    assert server._merchants["ownstore"].display_name == "Renamed store"
