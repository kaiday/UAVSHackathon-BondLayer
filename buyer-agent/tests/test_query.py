"""``/query`` and ``/chat`` with a mocked fetcher and a stubbed model.

No live merchant and no network. The model is stubbed rather than absent,
because it now decides the ranking: see ``conftest.stub_model``, which by
default answers in the order it was asked, so a stubbed run reproduces
``run_request``'s winner and the older assertions still bite.
"""

from __future__ import annotations

import sys
from pathlib import Path

CHAT_APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CHAT_APP))
sys.path.insert(0, str(CHAT_APP.parent.parent / "bondlayer" / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from src.agent import main, ucp_client  # noqa: E402


def _mock_fetch(merchant: str, query: str, *, extension: bool) -> dict:
    """One laptop per merchant; only voltway carries a verifiable record."""
    if merchant == "voltway":
        body = {
            "business": {"id": "voltway", "name": "Voltway"},
            "active_capabilities": {"dev.ucp.shopping.catalog.search": "2026-04-08"},
            "products": [{"id": "VOL-1", "title": "Test Laptop", "category": "laptop",
                          "price": {"amount": "920.00", "currency": "AUD"}, "attributes": {}}],
        }
        if extension:
            body["extensions"] = {
                "org.bondlayer.benefit_value": [{
                    "sku_id": "VOL-1", "issuer": "voltway.example",
                    "records": [{
                        # Ceiling above the reference shopper's $40 free_returns
                        # cap (bondlayer.valuation.reference_policy) -- the cap
                        # binds, not the ceiling.
                        "record": {"record_id": "r1", "benefit_type": "free_returns",
                                   "value_ceiling_aud": "100.00"},
                        "signature": "sig", "key_id": "k1", "signed": True,
                    }],
                }]
            }
        return body
    return {
        "business": {"id": merchant, "name": merchant.title()},
        "active_capabilities": {"dev.ucp.shopping.catalog.search": "2026-04-08"},
        "products": [{"id": f"{merchant.upper()}-1", "title": "Cheaper Laptop",
                      "category": "laptop", "price": {"amount": "900.00", "currency": "AUD"},
                      "attributes": {}}],
    }


def test_query_with_mocked_fetcher_and_no_key_returns_ranking_trace_and_prose(monkeypatch, stub_model):
    stub_model()
    monkeypatch.setattr(ucp_client, "discover_merchants", lambda *a: ["voltway", "citycircuit", "northgear"])
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(ucp_client, "make_fetcher", lambda *a, **k: _mock_fetch)
    monkeypatch.setattr(ucp_client, "make_verifier", lambda *a, **k: (lambda entry: True))

    client = TestClient(main.app)
    response = client.post("/query", json={"query": "a laptop", "bondlayer_enabled": True})

    assert response.status_code == 200
    body = response.json()

    assert body["ranked"], "no ranking returned"
    assert any(s["phase"] == "ranking" for s in body["steps"]), "no trace in the response"
    assert isinstance(body["recommendation"], str) and body["recommendation"]

    # Both model calls are on the trace, in the order they happened: the decode
    # that drove the search, then the ranking that decided the order.
    phases = [s["phase"] for s in body["steps"]]
    assert phases[0] == "intent_parse"
    assert phases[-1] == "rank"
    assert body["intent"], "the model's decode is not in the response"

    # The stub ranks in the order it was given, which is run_request's, so the
    # winner is still voltway -- and the credited figure is still computed and
    # still reported, even though it is no longer what ordered the list.
    assert body["winner"]["merchant"] == "voltway"
    assert float(body["winner"]["credited_aud"]) > 0


def test_query_returns_the_resolver_justification_for_every_offer(monkeypatch, stub_model):
    """``/query`` carries WHY, not just what and how much.

    The UI used to guess the clause-to-record binding from a keyword table,
    because ``run_request`` did not call the resolver. It does now, so the
    response carries the resolver's own ``resolved[]`` per offer and the page
    renders it instead of deriving it. A marker on screen means a
    ``ResolvedConstraint`` said so.

    The resolver still runs, and still explains every clause, even though the
    model now decides the order. The justification is not the ranking.
    """
    stub_model()
    monkeypatch.setattr(ucp_client, "discover_merchants", lambda *a: ["voltway", "citycircuit", "northgear"])
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(ucp_client, "make_fetcher", lambda *a, **k: _mock_fetch)
    monkeypatch.setattr(ucp_client, "make_verifier", lambda *a, **k: (lambda entry: True))

    client = TestClient(main.app)
    body = client.post("/query", json={
        "query": "a laptop I can return easily", "bondlayer_enabled": True,
    }).json()

    winner = body["winner"]
    assert winner["merchant"] == "voltway"
    assert winner["resolved"], "the winner carries no justification"
    assert all(r["note"].strip() for r in winner["resolved"])
    assert {"text", "kind", "satisfied", "evidence_record_id",
            "evidence_attribute", "note"} <= set(winner["resolved"][0])

    # The SERVICE clause is answered by the record that verified, by id.
    service = [r for r in winner["resolved"] if r["kind"] == "service"]
    assert service and service[0]["satisfied"]
    assert service[0]["evidence_record_id"] == "r1"

    # Every offer carries one, so the panes can be compared clause by clause.
    assert all("resolved" in offer and "unsatisfied" in offer
               for offer in body["ranked"])

    # The merchants with no record answer the same clause with the marker --
    # the resolver's exact string, which the page renders verbatim.
    for offer in body["ranked"]:
        if offer["merchant"] == "voltway":
            continue
        missed = [r for r in offer["resolved"] if r["kind"] == "service"]
        assert missed and not missed[0]["satisfied"]
        assert missed[0]["note"] == "← no catalogue attribute answers this"
        assert missed[0]["evidence_record_id"] is None


def test_the_page_renders_the_marker_and_never_guesses_it():
    """The keyword heuristic is gone, and must not come back.

    ``guessBenefitType`` mapped clause text to a benefit type in JavaScript and
    then hunted for a matching citation -- a rendering layer inventing the
    binding the resolver is responsible for.
    """
    page = (CHAT_APP / "src" / "agent" / "static" / "index.html").read_text(encoding="utf-8")

    assert "guessBenefitType" not in page
    assert "BENEFIT_HINTS" not in page
    # The marker is declared once, as a constant compared against the
    # resolver's note -- never assembled from the clause text.
    assert "no catalogue attribute answers this" in page
    assert "rc.note === UNANSWERED" in page
    # The three record states stay visually distinct.
    for state in ("rec-priced", "rec-unpriced", "rec-unsigned"):
        assert state in page


def _patch_common(monkeypatch):
    monkeypatch.setattr(ucp_client, "discover_merchants",
                        lambda *a: ["voltway", "citycircuit", "northgear"])
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(ucp_client, "make_fetcher", lambda *a, **k: _mock_fetch)
    monkeypatch.setattr(ucp_client, "make_verifier", lambda *a, **k: (lambda entry: True))


def test_the_model_decides_the_winner_not_the_arithmetic(monkeypatch, stub_model):
    """The point of the change: the model's order is the order.

    ``VOL-1`` wins on effective cost -- it is the only listing with a credited
    record, which is what the deterministic path ranks on. Here the model puts
    the record-less ``NORTHGEAR-1`` first anyway. If the response still leads
    with voltway, the model's ranking is decorative and this whole path is a
    narration of arithmetic rather than a decision.
    """
    stub_model(order=["NORTHGEAR-1", "VOL-1", "CITYCIRCUIT-1"])
    _patch_common(monkeypatch)

    body = TestClient(main.app).post(
        "/query", json={"query": "a laptop", "bondlayer_enabled": True},
    ).json()

    assert [r["sku_id"] for r in body["ranked"]][0] == "NORTHGEAR-1"
    assert body["winner"]["merchant"] == "northgear"
    # The deterministic figure is still computed and still reported for the
    # offer the model demoted -- shown beside the decision, not driving it.
    demoted = next(r for r in body["ranked"] if r["sku_id"] == "VOL-1")
    assert float(demoted["credited_aud"]) > 0
    assert body["winner"]["reasoning"]


def test_an_offer_the_model_omits_is_kept_not_dropped(monkeypatch, stub_model):
    """A model that forgets an offer must not disappear a merchant's listing."""
    stub_model(order=["NORTHGEAR-1"])
    _patch_common(monkeypatch)

    body = TestClient(main.app).post(
        "/query", json={"query": "a laptop", "bondlayer_enabled": True},
    ).json()

    skus = [r["sku_id"] for r in body["ranked"]]
    assert skus[0] == "NORTHGEAR-1"
    assert set(skus) == {"NORTHGEAR-1", "VOL-1", "CITYCIRCUIT-1"}


def test_the_rank_prompt_is_never_shown_the_effective_cost(monkeypatch, stub_model):
    """The model judges terms, so it must not be handed the arithmetic's answer."""
    seen = {}

    def capture(label, system, prompt):
        seen[label] = prompt
        if label == "intent_parse":
            return {"summary": "s", "category": None, "max_price_aud": None, "must_have": []}
        return {"ranking": [], "recommendation": "r"}

    _patch_common(monkeypatch)
    monkeypatch.setattr(main.llm, "complete_json", capture)

    TestClient(main.app).post("/query", json={"query": "a laptop", "bondlayer_enabled": True})

    prompt = seen["rank"]
    assert "shelf_price_aud" in prompt, "the model must see the price it is judging"
    assert "effective_cost" not in prompt
    assert "credited" not in prompt


def test_chat_asks_a_question_instead_of_searching_when_it_cannot(stub_model):
    """The conversation the one-shot box could not have."""
    stub_model(route={"action": "reply", "reply": "What will you use it for?"})

    body = TestClient(main.app).post("/chat", json={
        "messages": [{"role": "user", "content": "I need a new laptop"}],
    }).json()

    assert body["action"] == "reply"
    assert body["reply"] == "What will you use it for?"
    assert body["utterance"] is None


def test_chat_folds_the_conversation_into_one_sentence_to_send(stub_model):
    """When it does search, it searches for the whole conversation."""
    stub_model(route={"action": "search",
                      "utterance": "a laptop under $1,500 for video editing"})

    body = TestClient(main.app).post("/chat", json={
        "messages": [
            {"role": "user", "content": "I need a new laptop"},
            {"role": "assistant", "content": "What will you use it for?"},
            {"role": "user", "content": "video editing, under $1,500"},
        ],
    }).json()

    assert body["action"] == "search"
    assert body["utterance"] == "a laptop under $1,500 for video editing"
