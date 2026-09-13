"""``/query`` carries the merchant's own reading of the sentence (WS-J).

Same mocking pattern as ``test_query.py``: no live merchant, no network, no
model key. The fetcher and verifier are the existing fakes; the proposer is a
fake that answers for voltway and northgear and returns ``None`` (a 406) for
citycircuit. The one real-HTTP test drives ``make_proposer`` against the
merchant app in-process through ``TestClient``.
"""

from __future__ import annotations

import sys
from pathlib import Path

CHAT_APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CHAT_APP))
sys.path.insert(0, str(CHAT_APP.parent.parent / "bondlayer" / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from bondlayer.interpreter.parser import parse  # noqa: E402
from bondlayer.ucp.capabilities import BENEFIT_VALUE, INTENT_MATCH  # noqa: E402
from bondlayer.ucp.server import create_app  # noqa: E402

from src.agent import main, ucp_client  # noqa: E402
from tests.test_query import _mock_fetch  # noqa: E402

MERCHANTS = ["voltway", "citycircuit", "northgear"]

#: Every key ``/query`` returned before this workstream. All must survive.
PRE_EXISTING_KEYS = {
    "user_query", "bondlayer_enabled", "ucp_agent_header", "constraints", "steps",
    "ranked", "winner", "cheapest_shelf", "flipped", "recommendation", "bundles",
    "audit", "transcript",
}


class FakeProposer:
    """WS-H-shaped answers, decoded with the same parser the agent uses."""

    def __init__(self):
        self.calls: list[tuple[str, str, bool]] = []

    def __call__(self, merchant: str, utterance: str, *, extension: bool) -> dict | None:
        self.calls.append((merchant, utterance, extension))
        if merchant == "citycircuit":
            return None
        constraints = [{"text": c.text, "kind": c.kind.value, "interpretation": {}}
                       for c in parse(utterance)]
        sku = f"{merchant[:3].upper()}-1"
        return {
            "business": {"id": merchant, "name": merchant.title()},
            "active_capabilities": {INTENT_MATCH: "draft"},
            "decoded_intent": {
                "decoder": "rules", "utterance": utterance, "constraints": constraints,
                "unanswerable_from_catalogue": 1,
                "assumptions": ["Category read as 'laptop'."],
                "clarifying_question": None,
            },
            "proposals": [{
                "product": {"id": sku, "title": "Test Laptop", "category": "laptop",
                            "price": {"amount": "920.00", "currency": "AUD"}, "attributes": {}},
                "resolved": [{"text": c["text"], "kind": c["kind"], "satisfied": True,
                              "evidence_record_id": "r1" if c["kind"] == "service" else None,
                              "evidence_attribute": None if c["kind"] == "service" else "shelf_price",
                              "note": "Answered."} for c in constraints],
                "unsatisfied": [],
            }],
        }


def _patch(monkeypatch, proposer):
    monkeypatch.setattr(ucp_client, "discover_merchants", lambda *a: MERCHANTS)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(ucp_client, "make_fetcher", lambda *a, **k: _mock_fetch)
    monkeypatch.setattr(ucp_client, "make_verifier", lambda *a, **k: (lambda entry: True))
    monkeypatch.setattr(ucp_client, "make_proposer", lambda *a, **k: proposer)


def test_toggle_on_returns_three_merchant_decodes_next_to_the_ranking(monkeypatch, stub_model):
    stub_model()
    fake = FakeProposer()
    _patch(monkeypatch, fake)
    body = TestClient(main.app).post("/query", json={
        "query": "a laptop I can return easily", "bondlayer_enabled": True,
        "values_aud": {"free_returns": "40"},
    }).json()

    assert PRE_EXISTING_KEYS <= set(body)
    assert body["ranked"] and body["winner"]["merchant"] == "voltway"

    md = body["merchant_decodes"]
    assert md["kind"] == "merchant_decode"
    assert md["outcome"] == "ok"
    assert md["summary"].startswith("2 of 3 merchants decoded the request themselves")
    entries = md["merchant_decodes"]
    assert [e["merchant"] for e in entries] == MERCHANTS
    by = {e["merchant"]: e for e in entries}

    assert by["voltway"]["negotiated"] and by["northgear"]["negotiated"]
    assert by["citycircuit"] == {
        "merchant": "citycircuit", "negotiated": False, "decoded_intent": None,
        "proposals": [], "agreement": by["citycircuit"]["agreement"],
    }
    assert by["citycircuit"]["agreement"]["agreed"] == 0

    # Same parser on both seats: full agreement with the agent's decode.
    n = len(body["constraints"])
    assert n >= 2
    for m in ("voltway", "northgear"):
        assert by[m]["agreement"] == {
            **by[m]["agreement"], "agreed": n, "total": n, "merchant_only": [],
        }
        assert all(c["agree"] for c in by[m]["agreement"]["clauses"])
        assert by[m]["decoded_intent"]["assumptions"] == ["Category read as 'laptop'."]
        top = by[m]["proposals"][0]
        assert set(top) == {"sku_id", "title", "price", "currency", "resolved", "unsatisfied"}
        assert top["price"] == "920.00"

    # The sentence went to every merchant verbatim, with the extension on.
    assert fake.calls == [(m, "a laptop I can return easily", True) for m in MERCHANTS]

    # And it is in the trace as an ordinary step, findable by its detail kind.
    steps = [s for s in body["steps"] if s["detail"].get("kind") == "merchant_decode"]
    assert len(steps) == 1 and steps[0]["phase"] == "intent" and steps[0]["outcome"] == "ok"


def test_toggle_off_sends_nothing_and_returns_the_degraded_shape(monkeypatch, stub_model):
    stub_model()
    fake = FakeProposer()
    _patch(monkeypatch, fake)
    body = TestClient(main.app).post("/query", json={
        "query": "a laptop I can return easily", "bondlayer_enabled": False,
    }).json()

    assert PRE_EXISTING_KEYS <= set(body)
    assert fake.calls == []
    assert body["merchant_decodes"] == {
        "kind": "merchant_decode",
        "merchant_decodes": [],
        "outcome": "degraded",
        "summary": "Extension off: the shopper's sentence was not sent to any merchant; "
                   "only the agent decoded it.",
    }
    assert INTENT_MATCH not in body["ucp_agent_header"]


def test_the_header_declares_intent_match_only_when_the_toggle_is_on():
    on = ucp_client.agent_header(True).split(";")
    off = ucp_client.agent_header(False).split(";")
    assert on == [ucp_client.CATALOG_SEARCH, ucp_client.CATALOG_LOOKUP, BENEFIT_VALUE, INTENT_MATCH]
    assert off == [ucp_client.CATALOG_SEARCH, ucp_client.CATALOG_LOOKUP]


def test_make_proposer_against_the_real_merchant_app_in_process():
    """Real route, real negotiation: 200 for the publishing merchants, 406 ->
    None for the control, and no call at all when the extension is off."""
    client = TestClient(create_app())
    propose = ucp_client.make_proposer(client)
    utterance = "A laptop under $1,500 I can return easily"

    body = propose("voltway", utterance, extension=True)
    assert body is not None
    assert body["decoded_intent"]["decoder"] == "rules"
    assert INTENT_MATCH in body["active_capabilities"]
    assert body["proposals"] and len(body["proposals"]) <= 5

    assert propose("citycircuit", utterance, extension=True) is None
    assert propose("voltway", utterance, extension=False) is None


def test_the_page_renders_the_merchant_block_and_never_derives_it():
    page = (CHAT_APP / "src" / "agent" / "static" / "index.html").read_text(encoding="utf-8")
    assert "merchantDecodeHtml(d.merchant_decodes)" in page
    assert "did not negotiate intent_match" in page
    # The marks come from the agreement block, the resolver lines from the same
    # renderer the ranked offers use -- nothing is re-decided in the page.
    assert "c.agree && c.merchant" in page
    assert "constraintsHtml(top.resolved)" in page
    assert "not the ranking" in page
