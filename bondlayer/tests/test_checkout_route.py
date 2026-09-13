"""The merchant-side checkout route: the chosen offer becomes an order that
binds the signed records the agent relied on.

What these tests hold:

- ``dev.ucp.shopping.checkout`` is base UCP: every merchant declares it, the
  control included, and it is negotiated like any other -- no header, 406.
- The loop closes: the records ``intent.propose`` cited as evidence are the
  records checkout honours, and every one of them comes back inside the order
  as the same signed envelope, verifiable against the profile's keys.
- Every refusal names its test in plain words: unsigned, out of scope, not
  published, expired.
- The benefit keys are gated by their own negotiation, exactly as on
  ``catalog.search``: present when negotiated, absent otherwise. The control
  serves a plain order on the same route.
- The order id is a content hash: identical body, identical id; different
  honoured set, different id. No clock, no store.
- Payment is out of scope and the response says so. The merchant never
  receives a shopper's valuation policy: the body forbids the field.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from bondlayer.ucp import server
from bondlayer.ucp.capabilities import (
    BENEFIT_VALUE,
    CATALOG_LOOKUP,
    CATALOG_SEARCH,
    CHECKOUT,
    INTENT_MATCH,
)
from bondlayer.ucp.checkout import (
    REASON_NOT_PUBLISHED,
    REASON_UNSIGNED,
    STATUS_CONFIRMED,
    judge,
)
from bondlayer.ucp.server import create_app

R01 = (
    "A laptop under $1,500 I can return easily if it turns out not to suit my work, "
    "from a brand that actually repairs things"
)

FULL = ";".join([CATALOG_SEARCH, CATALOG_LOOKUP, BENEFIT_VALUE, INTENT_MATCH, CHECKOUT])
NO_BENEFIT = ";".join([CATALOG_SEARCH, CATALOG_LOOKUP, INTENT_MATCH, CHECKOUT])
NO_CHECKOUT = ";".join([CATALOG_SEARCH, CATALOG_LOOKUP, BENEFIT_VALUE, INTENT_MATCH])

URL = "/{merchant}/ucp/checkout"


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


def _checkout(client, merchant: str, header: str | None, items, cited=None, **body):
    headers = {"UCP-Agent": header} if header is not None else {}
    payload = {"items": items, "cited_record_ids": list(cited or []), **body}
    return client.post(URL.format(merchant=merchant), json=payload, headers=headers)


def _first_laptop(merchant: str):
    return next(s for s in server._catalog[merchant] if s.category == "laptop")


# --- discovery ----------------------------------------------------------------------


def test_every_merchant_declares_checkout_as_a_base_capability(client):
    for merchant in ("voltway", "northgear", "citycircuit"):
        profile = client.get(f"/{merchant}/.well-known/ucp").json()
        assert CHECKOUT in profile["capabilities"], merchant
        assert profile["capabilities"][CHECKOUT] == [{"version": "2026-04-08"}]
        # It is base UCP, not one of ours: never listed as an extension.
        assert CHECKOUT not in profile["extensions"]


# --- negotiation --------------------------------------------------------------------


def test_not_negotiated_is_406(client):
    sku = _first_laptop("voltway")
    r = _checkout(client, "voltway", NO_CHECKOUT, [{"sku_id": sku.sku_id, "quantity": 1}])
    assert r.status_code == 406
    assert "checkout was not negotiated" in r.text
    # No header at all is the plain-UCP default: search and lookup only.
    r = _checkout(client, "voltway", None, [{"sku_id": sku.sku_id, "quantity": 1}])
    assert r.status_code == 406


def test_unknown_merchant_is_404(client):
    r = _checkout(client, "nowhere", FULL, [{"sku_id": "X", "quantity": 1}])
    assert r.status_code == 404


# --- the full loop: propose, then check out what was proposed ------------------------


@pytest.fixture(scope="module")
def r01_loop(client):
    proposed = client.post(
        "/voltway/ucp/intent/propose",
        json={"utterance": R01},
        headers={"UCP-Agent": FULL},
    )
    assert proposed.status_code == 200, proposed.text
    top = proposed.json()["proposals"][0]
    cited = [
        r["evidence_record_id"] for r in top["resolved"] if r["evidence_record_id"]
    ]
    assert cited, "R01 is answered from verified records"
    order = _checkout(
        client, "voltway", FULL,
        [{"sku_id": top["product"]["id"], "quantity": 1}],
        cited=cited, agent_ref="r01-demo",
    )
    assert order.status_code == 200, order.text
    return top, cited, order.json()


def test_r01_every_cited_record_is_honoured(r01_loop):
    _, cited, body = r01_loop
    verdicts = {v["record_id"]: v for v in body["honoured_benefits"]}
    assert set(verdicts) == set(cited)
    for record_id in cited:
        v = verdicts[record_id]
        assert set(v) == {"record_id", "honoured", "reason", "sku_id"}
        assert v["honoured"] is True, v
        assert "verified" in v["reason"]
        assert v["sku_id"] == body["order"]["line_items"][0]["sku_id"]


def test_r01_extension_carries_exactly_the_honoured_envelopes_signed(r01_loop):
    _, cited, body = r01_loop
    envelopes = body["extensions"][BENEFIT_VALUE]
    assert sorted(e["record"]["record_id"] for e in envelopes) == sorted(cited)
    for e in envelopes:
        assert set(e) == {"record", "signature", "key_id", "signed"}
        assert e["signed"] is True
        assert e["signature"] and e["key_id"]
        assert e["record"]["issuer"] == "voltway.example"


def test_r01_envelopes_are_the_ones_catalog_search_serves(client, r01_loop):
    top, _, body = r01_loop
    served = client.get(
        f"/voltway/ucp/catalog/lookup?sku_id={top['product']['id']}",
        headers={"UCP-Agent": FULL},
    ).json()["extensions"][BENEFIT_VALUE][0]["records"]
    by_id = {e["record"]["record_id"]: e for e in served}
    for e in body["extensions"][BENEFIT_VALUE]:
        assert e == by_id[e["record"]["record_id"]], "same envelope, byte for byte"


def test_r01_order_shape_and_totals(r01_loop):
    top, _, body = r01_loop
    assert set(body) == {"business", "active_capabilities", "order",
                         "honoured_benefits", "extensions"}
    assert body["business"] == {"id": "voltway", "name": "Voltway"}
    assert CHECKOUT in body["active_capabilities"]
    order = body["order"]
    assert set(order) == {"order_id", "status", "line_items", "subtotal", "payment", "agent_ref"}
    assert order["status"] == STATUS_CONFIRMED == "confirmed_awaiting_payment"
    assert len(order["order_id"]) == 16 and int(order["order_id"], 16) >= 0
    assert order["agent_ref"] == "r01-demo"
    [line] = order["line_items"]
    assert line["sku_id"] == top["product"]["id"]
    assert line["title"] == top["product"]["title"]
    assert line["quantity"] == 1
    assert line["unit_price"] == top["product"]["price"]
    assert line["line_total"] == top["product"]["price"]
    assert order["subtotal"] == top["product"]["price"]
    assert order["payment"]["status"] == "out_of_scope"
    assert "no funds move" in order["payment"]["note"]


# --- refusals name their test -------------------------------------------------------


def test_unsigned_claim_is_not_honoured_but_a_real_record_beside_it_is(client):
    sku = _first_laptop("northgear")
    r = _checkout(client, "northgear", FULL, [{"sku_id": sku.sku_id, "quantity": 1}],
                  cited=["ng-sustainability-claim", "ng-returns-45"])
    assert r.status_code == 200, r.text
    body = r.json()
    verdicts = {v["record_id"]: v for v in body["honoured_benefits"]}
    assert verdicts["ng-sustainability-claim"]["honoured"] is False
    assert verdicts["ng-sustainability-claim"]["reason"] == REASON_UNSIGNED
    assert verdicts["ng-sustainability-claim"]["sku_id"] is None
    assert verdicts["ng-returns-45"]["honoured"] is True
    # Only the honoured one rides the extension; the unsigned claim is not
    # smuggled into the order as proof of anything.
    ids = [e["record"]["record_id"] for e in body["extensions"][BENEFIT_VALUE]]
    assert ids == ["ng-returns-45"]


def test_record_scoped_to_another_category_is_not_honoured(client):
    sku = _first_laptop("voltway")
    r = _checkout(client, "voltway", FULL, [{"sku_id": sku.sku_id, "quantity": 1}],
                  cited=["vw-tradein-phone-450", "vw-tradein-laptop-700"])
    assert r.status_code == 200
    verdicts = {v["record_id"]: v for v in r.json()["honoured_benefits"]}
    phone = verdicts["vw-tradein-phone-450"]
    assert phone["honoured"] is False
    assert phone["reason"] == "record scope 'phone' does not cover category 'laptop'"
    laptop = verdicts["vw-tradein-laptop-700"]
    assert laptop["honoured"] is True
    assert "subject to conditions: trade_in_device" in laptop["reason"]


def test_unknown_record_id_is_not_published_by_this_merchant(client):
    sku = _first_laptop("voltway")
    # A NorthGear id cited at Voltway is a record Voltway has never heard of.
    r = _checkout(client, "voltway", FULL, [{"sku_id": sku.sku_id, "quantity": 1}],
                  cited=["ng-returns-45", "made-up-id"])
    verdicts = {v["record_id"]: v for v in r.json()["honoured_benefits"]}
    for rid in ("ng-returns-45", "made-up-id"):
        assert verdicts[rid]["honoured"] is False
        assert verdicts[rid]["reason"] == REASON_NOT_PUBLISHED
    assert r.json()["extensions"][BENEFIT_VALUE] == []


def test_expired_record_is_refused_as_expired():
    """No record in ``data/`` has expired, so the branch is pinned through the
    pure judgement with a clock set after every window closes."""
    from bondlayer.records import load_signed
    from bondlayer.ucp.intent import verified_records
    from bondlayer.ucp.profile import load_merchants
    from bondlayer.ucp.records import RECORDS, load_records

    merchant = load_merchants()["voltway"]
    sku = _first_laptop("voltway")
    parsed = load_signed(RECORDS / "voltway.signed.json")
    verified = frozenset(r.record.record_id for r in verified_records(merchant))
    assert "vw-returns-60" in verified
    [v] = judge(
        ["vw-returns-60"], [sku],
        published=load_records("voltway"), parsed=parsed, verified_ids=verified,
        now=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )
    assert v["honoured"] is False
    assert v["reason"].startswith("expired")
    # And with today's clock, the same record is honoured.
    [v] = judge(
        ["vw-returns-60"], [sku],
        published=load_records("voltway"), parsed=parsed, verified_ids=verified,
    )
    assert v["honoured"] is True


def test_duplicate_citations_are_judged_once(client):
    sku = _first_laptop("voltway")
    r = _checkout(client, "voltway", FULL, [{"sku_id": sku.sku_id, "quantity": 1}],
                  cited=["vw-returns-60", "vw-returns-60"])
    body = r.json()
    assert [v["record_id"] for v in body["honoured_benefits"]] == ["vw-returns-60"]
    assert len(body["extensions"][BENEFIT_VALUE]) == 1


# --- the benefit keys are gated by their own negotiation --------------------------------


def test_control_merchant_serves_a_plain_order_on_the_same_route(client):
    sku = _first_laptop("citycircuit")
    r = _checkout(client, "citycircuit", FULL, [{"sku_id": sku.sku_id, "quantity": 2}],
                  cited=["vw-returns-60"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"business", "active_capabilities", "order"}
    assert "honoured_benefits" not in body and "extensions" not in body
    assert BENEFIT_VALUE not in body["active_capabilities"]
    assert CHECKOUT in body["active_capabilities"]
    assert body["order"]["status"] == STATUS_CONFIRMED
    assert body["order"]["line_items"][0]["quantity"] == 2
    assert body["order"]["subtotal"]["amount"] == str(sku.shelf_price * 2)


def test_without_benefit_value_the_keys_are_absent_and_the_order_still_comes(client):
    sku = _first_laptop("voltway")
    items = [{"sku_id": sku.sku_id, "quantity": 1}]
    plain = _checkout(client, "voltway", NO_BENEFIT, items, cited=["vw-returns-60"])
    assert plain.status_code == 200
    body = plain.json()
    assert set(body) == {"business", "active_capabilities", "order"}
    # The order id still binds the honoured set: the same body, judged the
    # same way, gets the same id whether or not the agent can see the verdicts.
    rich = _checkout(client, "voltway", FULL, items, cited=["vw-returns-60"]).json()
    assert body["order"] == rich["order"]


# --- validation -----------------------------------------------------------------------


def test_unknown_sku_is_404(client):
    r = _checkout(client, "voltway", FULL, [{"sku_id": "VOL-9999", "quantity": 1}])
    assert r.status_code == 404
    # A NorthGear sku at Voltway is unknown to Voltway.
    ng = _first_laptop("northgear")
    r = _checkout(client, "voltway", FULL, [{"sku_id": ng.sku_id, "quantity": 1}])
    assert r.status_code == 404


def test_the_merchant_does_not_accept_a_shopper_policy(client):
    sku = _first_laptop("voltway")
    for leak in ("shopper_policy", "policy", "values_aud"):
        r = _checkout(client, "voltway", FULL, [{"sku_id": sku.sku_id, "quantity": 1}],
                      **{leak: {"free_returns": "40"}})
        assert r.status_code == 422, leak
        assert "extra" in r.text.lower()


def test_body_is_validated(client):
    sku = _first_laptop("voltway")
    assert _checkout(client, "voltway", FULL, []).status_code == 422
    assert _checkout(client, "voltway", FULL,
                     [{"sku_id": sku.sku_id, "quantity": 0}]).status_code == 422
    assert _checkout(client, "voltway", FULL,
                     [{"sku_id": sku.sku_id}]).status_code == 422
    assert _checkout(client, "voltway", FULL,
                     [{"sku_id": sku.sku_id, "quantity": 1, "price": "1"}]).status_code == 422


def test_quantity_beyond_published_stock_is_409(client, monkeypatch):
    """The checkout gate accepts numeric stock and numeric-string stock."""
    sku = _first_laptop("voltway")

    def with_stock(value):
        # `_catalog` is a dict, so monkeypatch restores the original list after
        # the test; the seeded Sku objects themselves are never mutated.
        patched = [
            dataclasses.replace(s, attributes={**s.attributes, "stock": value})
            if s.sku_id == sku.sku_id else s
            for s in server._catalog["voltway"]
        ]
        monkeypatch.setitem(server._catalog, "voltway", patched)

    with_stock(2)
    over = _checkout(client, "voltway", FULL, [{"sku_id": sku.sku_id, "quantity": 3}])
    assert over.status_code == 409
    assert over.json() == {"detail": "insufficient stock", "sku_id": sku.sku_id, "available": 2}
    within = _checkout(client, "voltway", FULL, [{"sku_id": sku.sku_id, "quantity": 2}])
    assert within.status_code == 200
    # The CSV publishes stock as text; a numeric string still gates.
    with_stock("1")
    assert _checkout(client, "voltway", FULL,
                     [{"sku_id": sku.sku_id, "quantity": 2}]).status_code == 409


def test_a_listing_without_a_stock_figure_never_blocks(client, monkeypatch):
    sku = _first_laptop("voltway")
    monkeypatch.setitem(server._catalog, "voltway", [
        dataclasses.replace(s, attributes={k: v for k, v in s.attributes.items() if k != "stock"})
        if s.sku_id == sku.sku_id else s for s in server._catalog["voltway"]
    ])
    r = _checkout(client, "voltway", FULL, [{"sku_id": sku.sku_id, "quantity": 50}])
    assert r.status_code == 200


# --- determinism ------------------------------------------------------------------------


def test_identical_bodies_yield_identical_order_ids(client):
    sku = _first_laptop("voltway")
    items = [{"sku_id": sku.sku_id, "quantity": 1}]
    a = _checkout(client, "voltway", FULL, items, cited=["vw-returns-60"]).json()
    b = _checkout(client, "voltway", FULL, items, cited=["vw-returns-60"]).json()
    assert a["order"]["order_id"] == b["order"]["order_id"]
    assert a == b, "stateless: nothing in the response depends on the call"


def test_citation_order_does_not_change_the_order_id(client):
    sku = _first_laptop("voltway")
    items = [{"sku_id": sku.sku_id, "quantity": 1}]
    a = _checkout(client, "voltway", FULL, items,
                  cited=["vw-returns-60", "vw-repairability-parts-5y"]).json()
    b = _checkout(client, "voltway", FULL, items,
                  cited=["vw-repairability-parts-5y", "vw-returns-60"]).json()
    assert a["order"]["order_id"] == b["order"]["order_id"]


def test_a_different_honoured_set_yields_a_different_order_id(client):
    sku = _first_laptop("voltway")
    items = [{"sku_id": sku.sku_id, "quantity": 1}]
    none = _checkout(client, "voltway", FULL, items).json()["order"]["order_id"]
    one = _checkout(client, "voltway", FULL, items,
                    cited=["vw-returns-60"]).json()["order"]["order_id"]
    two = _checkout(client, "voltway", FULL, items,
                    cited=["vw-returns-60", "vw-repairability-parts-5y"]).json()["order"]["order_id"]
    assert len({none, one, two}) == 3
    # A citation that is *not* honoured does not enter the id: the order binds
    # what it honours, not what was asked.
    refused = _checkout(client, "voltway", FULL, items,
                        cited=["vw-returns-60", "made-up-id"]).json()["order"]["order_id"]
    assert refused == one


def test_quantity_changes_the_order_id(client):
    sku = _first_laptop("voltway")
    a = _checkout(client, "voltway", FULL, [{"sku_id": sku.sku_id, "quantity": 1}]).json()
    b = _checkout(client, "voltway", FULL, [{"sku_id": sku.sku_id, "quantity": 2}]).json()
    assert a["order"]["order_id"] != b["order"]["order_id"]


# --- the existing routes are untouched ----------------------------------------------------


def test_catalog_search_ignores_the_new_capability(client):
    with_it = client.get("/voltway/ucp/catalog/search?category=laptop&limit=3",
                         headers={"UCP-Agent": FULL}).json()
    without = client.get("/voltway/ucp/catalog/search?category=laptop&limit=3",
                         headers={"UCP-Agent": NO_CHECKOUT}).json()
    assert with_it["products"] == without["products"]
    assert with_it["extensions"] == without["extensions"]
    assert CHECKOUT in with_it["active_capabilities"]
    assert CHECKOUT not in without["active_capabilities"]
