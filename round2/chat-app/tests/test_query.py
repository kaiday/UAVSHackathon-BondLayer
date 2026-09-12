"""``/query`` with a mocked fetcher and no model key.

The one test the brief asks for: no live merchant, no network, no
``OPENAI_API_KEY`` -- and the endpoint still returns a ranking, the trace, and
a prose string. Ranking must come from ``run_request``'s arithmetic, never
from a model; with no key, the prose is the deterministic template.
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


def test_query_with_mocked_fetcher_and_no_key_returns_ranking_trace_and_prose(monkeypatch):
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
    prose_step = next(s for s in body["steps"] if s["phase"] == "prose")
    assert prose_step["outcome"] == "template"
    assert "no model key" in prose_step["summary"]

    # Ranking is the arithmetic, not the model: voltway's credited record
    # brings it below the cheaper, record-less competitors.
    assert body["winner"]["merchant"] == "voltway"
    assert float(body["winner"]["credited_aud"]) > 0


def test_query_returns_the_resolver_justification_for_every_offer(monkeypatch):
    """``/query`` carries WHY, not just what and how much.

    The UI used to guess the clause-to-record binding from a keyword table,
    because ``run_request`` did not call the resolver. It does now, so the
    response carries the resolver's own ``resolved[]`` per offer and the page
    renders it instead of deriving it. A marker on screen means a
    ``ResolvedConstraint`` said so.
    """
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
