"""The merchant-side intent route: the sentence in, a justified proposal out.

What these tests hold:

- The capability is declared by exactly the merchants that publish the benefit
  extension, and negotiated like any other -- an agent that did not declare it
  gets 406, and the control merchant never serves it.
- The decode is explained, not asserted: every clause carries its kind and the
  merchant's reading of it, the unanswerable ones are counted, and a request
  that names no product earns one clarifying question and still gets answers.
- Evidence is only ever a verified record, and when the benefit extension is
  also negotiated every cited record is visible in the extension block, signed.
- The benefit block is gated by its own negotiation, exactly as on
  ``catalog.search``: present when negotiated, absent -- never empty --
  otherwise, with the proposals unchanged.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bondlayer.ucp.capabilities import (
    BENEFIT_VALUE,
    CATALOG_LOOKUP,
    CATALOG_SEARCH,
    INTENT_MATCH,
)
from bondlayer.ucp.server import create_app

R01 = (
    "A laptop under $1,500 I can return easily if it turns out not to suit my work, "
    "from a brand that actually repairs things"
)

FULL = ";".join([CATALOG_SEARCH, CATALOG_LOOKUP, BENEFIT_VALUE, INTENT_MATCH])
INTENT_ONLY = ";".join([CATALOG_SEARCH, CATALOG_LOOKUP, INTENT_MATCH])
BENEFIT_ONLY = ";".join([CATALOG_SEARCH, CATALOG_LOOKUP, BENEFIT_VALUE])

URL = "/{merchant}/ucp/intent/propose"


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


def _propose(client, merchant: str, header: str | None, utterance: str = R01, **body):
    headers = {"UCP-Agent": header} if header is not None else {}
    return client.post(
        URL.format(merchant=merchant),
        json={"utterance": utterance, **body},
        headers=headers,
    )


# --- discovery --------------------------------------------------------------


def test_publishing_merchants_declare_intent_match_as_an_extension_of_search(client):
    for merchant in ("voltway", "northgear"):
        ext = client.get(f"/{merchant}/.well-known/ucp").json()["extensions"]
        assert INTENT_MATCH in ext, merchant
        declared = ext[INTENT_MATCH][0]
        assert declared["version"] == "draft"
        assert declared["extends"] == [CATALOG_SEARCH]
        assert declared["spec"].startswith("https://bondlayer.example/")
        assert declared["schema"].startswith("https://bondlayer.example/")
        # The benefit extension is still declared alongside it, untouched.
        assert BENEFIT_VALUE in ext


def test_control_merchant_does_not_declare_intent_match(client):
    ext = client.get("/citycircuit/.well-known/ucp").json()["extensions"]
    assert INTENT_MATCH not in ext
    assert ext == {}


# --- negotiation --------------------------------------------------------------


def test_not_negotiated_is_406_not_a_degraded_200(client):
    # An agent that declared the benefit extension but not intent_match.
    r = _propose(client, "voltway", BENEFIT_ONLY)
    assert r.status_code == 406
    assert "intent.propose was not negotiated" in r.text
    # No header at all: plain UCP, which never negotiates an extension.
    assert _propose(client, "voltway", None).status_code == 406


def test_control_never_negotiates_it_even_when_the_agent_declares_it(client):
    r = _propose(client, "citycircuit", FULL)
    assert r.status_code == 406


def test_unknown_merchant_is_404(client):
    assert _propose(client, "nowhere", FULL).status_code == 404


def test_body_is_validated(client):
    r = client.post(URL.format(merchant="voltway"), json={"utterance": ""},
                    headers={"UCP-Agent": FULL})
    assert r.status_code == 422
    r = client.post(URL.format(merchant="voltway"), json={"utterance": "   "},
                    headers={"UCP-Agent": FULL})
    assert r.status_code == 422
    r = _propose(client, "voltway", FULL, limit=0)
    assert r.status_code == 422
    r = _propose(client, "voltway", FULL, limit=101)
    assert r.status_code == 422


# --- R01 with the full header -------------------------------------------------


@pytest.fixture(scope="module")
def r01_full(client):
    r = _propose(client, "voltway", FULL)
    assert r.status_code == 200, r.text
    return r.json()


def test_r01_decodes_into_one_clause_of_each_kind(r01_full):
    decoded = r01_full["decoded_intent"]
    assert decoded["decoder"] == "rules"
    assert decoded["utterance"] == R01
    constraints = decoded["constraints"]
    assert len(constraints) == 4
    assert sorted(c["kind"] for c in constraints) == ["hard", "service", "soft", "values"]
    for c in constraints:
        assert set(c) == {"text", "kind", "interpretation"}
        assert c["text"], "the clause is echoed as the shopper said it"

    by_kind = {c["kind"]: c for c in constraints}
    # HARD: the category and the ceiling, decimal as a string.
    assert by_kind["hard"]["interpretation"] == {"category": "laptop", "max_price_aud": "1500"}
    # SOFT: the resolver's ordering signal and the typed attributes it uses.
    soft = by_kind["soft"]["interpretation"]
    assert soft["signal"] and "ram_gb" in soft["attributes"]
    # SERVICE and VALUES: the benefit type a record must carry to answer them.
    assert by_kind["service"]["interpretation"] == {"benefit_type": "free_returns"}
    assert by_kind["values"]["interpretation"] == {"benefit_type": "repairability"}


def test_r01_counts_the_clauses_no_catalogue_can_answer(r01_full):
    decoded = r01_full["decoded_intent"]
    assert decoded["unanswerable_from_catalogue"] == 2
    assert decoded["clarifying_question"] is None, "R01 names a laptop; nothing to ask"


def test_r01_assumptions_are_plain_true_sentences(r01_full):
    assumptions = r01_full["decoded_intent"]["assumptions"]
    assert assumptions and all(isinstance(a, str) and a.endswith(".") for a in assumptions)
    assert any("hard ceiling" in a and "'under'" in a for a in assumptions)
    # One sentence per clause that only a published record can answer.
    record_only = [a for a in assumptions if "published benefit record" in a]
    assert len(record_only) == 2
    assert any("I can return easily" in a for a in record_only)
    assert any("repairs things" in a for a in record_only)
    # The category *was* stated, so the "no category" assumption must not appear.
    assert not any("No product category was stated" in a for a in assumptions)


def test_r01_proposals_respect_the_hard_clause(r01_full):
    proposals = r01_full["proposals"]
    assert proposals, "voltway has laptops under $1,500"
    for p in proposals:
        assert set(p) == {"product", "resolved", "unsatisfied"}
        assert p["product"]["category"] == "laptop"
        assert float(p["product"]["price"]["amount"]) <= 1500
        # One resolved entry per clause the shopper said, in a fixed shape.
        assert len(p["resolved"]) == 4
        for r in p["resolved"]:
            assert set(r) == {"text", "kind", "satisfied", "evidence_record_id",
                              "evidence_attribute", "note"}
        for u in p["unsatisfied"]:
            assert set(u) == {"text", "kind"}


def test_r01_products_are_exactly_what_catalog_search_serves(client, r01_full):
    # Same helper, same bytes: a product on this route is a product on search.
    search = client.get(
        "/voltway/ucp/catalog/search?category=laptop&max_price=1500&limit=100",
        headers={"UCP-Agent": FULL},
    ).json()["products"]
    by_id = {p["id"]: p for p in search}
    for p in r01_full["proposals"]:
        assert p["product"] == by_id[p["product"]["id"]]
    for key in ("merchant", "model_key"):
        assert all(key not in p["product"]["attributes"] for p in r01_full["proposals"])


def test_r01_every_cited_record_is_served_signed_in_the_extension(r01_full):
    assert "extensions" in r01_full
    blocks = r01_full["extensions"][BENEFIT_VALUE]
    assert len(blocks) == len(r01_full["proposals"]), "one block per proposal, in order"
    cited_anywhere = False
    for p, block in zip(r01_full["proposals"], blocks):
        assert block["sku_id"] == p["product"]["id"]
        assert block["issuer"] == "voltway.example"
        served = {e["record"]["record_id"]: e for e in block["records"]}
        for r in p["resolved"]:
            if r["evidence_record_id"] is None:
                continue
            cited_anywhere = True
            assert r["satisfied"] is True
            assert r["kind"] in ("service", "values")
            entry = served[r["evidence_record_id"]]
            assert entry["signed"] is True
    assert cited_anywhere, "voltway publishes verified returns and repairability records"


def test_r01_answers_both_record_clauses_from_verified_records(r01_full):
    top = r01_full["proposals"][0]
    by_kind = {r["kind"]: r for r in top["resolved"]}
    assert by_kind["service"]["evidence_record_id"]
    assert by_kind["values"]["evidence_record_id"]
    assert "verified record" in by_kind["service"]["note"]
    assert top["unsatisfied"] == []


def test_active_capabilities_are_echoed(r01_full):
    assert INTENT_MATCH in r01_full["active_capabilities"]
    assert BENEFIT_VALUE in r01_full["active_capabilities"]


# --- the benefit block is gated by its own negotiation --------------------------


def test_without_benefit_value_the_extension_is_absent_and_proposals_still_come(client, r01_full):
    r = _propose(client, "voltway", INTENT_ONLY)
    assert r.status_code == 200
    body = r.json()
    assert "extensions" not in body, "absent, not empty"
    assert BENEFIT_VALUE not in body["active_capabilities"]
    assert INTENT_MATCH in body["active_capabilities"]
    # The resolver still ran with the verified records: the proposals and the
    # justification are identical. The agent simply cannot see the raw records.
    assert body["proposals"] == r01_full["proposals"]
    assert body["decoded_intent"] == r01_full["decoded_intent"]


# --- low confidence: ask, do not fail -------------------------------------------


def test_no_category_earns_one_question_and_still_answers(client):
    r = _propose(client, "voltway", FULL,
                 utterance="something light I can carry every day, under 1.3kg")
    assert r.status_code == 200
    body = r.json()
    decoded = body["decoded_intent"]
    assert isinstance(decoded["clarifying_question"], str) and decoded["clarifying_question"]
    assert any("category" in a for a in decoded["assumptions"])
    assert decoded["unanswerable_from_catalogue"] == 0
    kinds = {c["kind"] for c in decoded["constraints"]}
    assert "hard" in kinds and "soft" in kinds
    # The weight bound is still a real filter; ambiguity about *what* never
    # becomes a hard failure about *anything*.
    assert body["proposals"], "the shelf is still answered, over every category"
    for p in body["proposals"]:
        assert float(p["product"]["attributes"]["weight_kg"]) <= 1.3


# --- verification gate -------------------------------------------------------------


def test_unverifiable_records_never_reach_the_resolver():
    from bondlayer.ucp.intent import verified_records
    from bondlayer.ucp.profile import load_merchants
    from bondlayer.ucp.records import load_records

    merchants = load_merchants()
    # NorthGear plants one unsigned sustainability claim. It is *served*...
    served = load_records("northgear")
    unsigned = [e["record"]["record_id"] for e in served if not e["signed"]]
    assert unsigned, "the planted unsigned claim must be published to be seen losing"
    # ...and it is never handed to the resolver.
    verified = {r.record.record_id for r in verified_records(merchants["northgear"])}
    assert verified
    assert not (verified & set(unsigned))
    assert len(verified) == len(served) - len(unsigned)
    # The control signs nothing and has no key, so nothing of its can verify.
    assert verified_records(merchants["citycircuit"]) == []


def test_limit_truncates_the_proposals(client):
    r = _propose(client, "voltway", FULL, limit=2)
    assert r.status_code == 200
    body = r.json()
    assert len(body["proposals"]) == 2
    assert len(body["extensions"][BENEFIT_VALUE]) == 2


# --- the existing routes are untouched ----------------------------------------------


def test_catalog_search_ignores_the_new_capability(client):
    with_it = client.get("/voltway/ucp/catalog/search?category=laptop&limit=3",
                         headers={"UCP-Agent": FULL}).json()
    without = client.get("/voltway/ucp/catalog/search?category=laptop&limit=3",
                         headers={"UCP-Agent": BENEFIT_ONLY}).json()
    assert with_it["products"] == without["products"]
    assert with_it["extensions"] == without["extensions"]
    # The only difference is the echo of what was negotiated.
    assert INTENT_MATCH in with_it["active_capabilities"]
    assert INTENT_MATCH not in without["active_capabilities"]
