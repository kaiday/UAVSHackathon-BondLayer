"""Invariants for the composition root.

These encode the two rules the module is built on: fail closed, degrade
honestly. They keep the demo truthful while components are missing, which is
the state we are actually in today.
"""

import json
from decimal import Decimal

from bondlayer.agent import DEFAULT_POLICY, Outcome, Phase, policy_from, run_request
from bondlayer.interpreter.parser import parse
from bondlayer.types import BenefitType, ShopperPolicy


def _body(merchant, sku, price, records=None, extension=True):
    body = {
        "business": {"id": merchant, "name": merchant.title()},
        "active_capabilities": {"dev.ucp.shopping.catalog.search": "2026-04-08"},
        "products": [{"id": sku, "title": "Surface Laptop Go 3",
                      "category": "laptop",
                      "price": {"amount": price, "currency": "AUD"},
                      "attributes": {"ram_gb": 8}}],
    }
    if extension:
        body["extensions"] = {
            "org.bondlayer.benefit_value": [
                {"sku_id": sku, "issuer": f"{merchant}.example",
                 "records": records or []}
            ]
        }
    return body


def _record(rid, btype, ceiling, signed=True):
    return {"record": {"record_id": rid, "benefit_type": btype,
                       "value_ceiling_aud": ceiling},
            "signature": "sig" if signed else None,
            "key_id": "k1" if signed else None,
            "signed": signed}


def test_no_verifier_credits_nothing():
    """Fail closed. An unwired verifier must not read as 'assume verified'."""
    def fetch(m, q, *, extension):
        return _body(m, "V-1", "1000.00", [_record("r1", "free_returns", "72.00")])

    run = run_request("laptop", ["voltway"], fetch)
    assert run.ranked[0].credited == Decimal("0")
    assert run.ranked[0].effective_cost == Decimal("1000.00")
    assert any(s.phase is Phase.VERIFICATION and s.outcome is Outcome.ABSENT
               for s in run.steps)


def test_unverified_record_is_displayed_but_never_valued():
    def fetch(m, q, *, extension):
        return _body(m, "V-1", "1000.00",
                     [_record("r1", "free_returns", "72.00", signed=False)])

    run = run_request("laptop", ["voltway"], fetch,
                      verify=lambda e: bool(e["signature"]))
    top = run.ranked[0]
    assert top.credited == Decimal("0")
    assert top.records_seen == 1 and top.records_verified == 0
    assert top.citations[0]["cited"] is False
    assert "never valued" in top.citations[0]["why"]


def test_values_claim_is_cited_but_credits_zero():
    """value_ceiling_aud None = validated, citable, worth exactly $0."""
    def fetch(m, q, *, extension):
        return _body(m, "V-1", "1000.00", [_record("r1", "repairability", None)])

    run = run_request("laptop", ["voltway"], fetch, verify=lambda e: True)
    cite = run.ranked[0].citations[0]
    assert cite["credited"] == "0.00"
    assert cite["cited"] is True
    assert run.ranked[0].credited == Decimal("0")


def test_inflating_a_ceiling_is_bounded_by_the_shopper_policy():
    """The honest claim is not 'inflation changes nothing'. It is that a
    merchant can never be credited more than the shopper thinks it is worth."""
    def fetch_at(ceiling):
        def fetch(m, q, *, extension):
            return _body(m, "V-1", "1000.00",
                         [_record("r1", "free_returns", ceiling)])
        return fetch

    honest = run_request("l", ["voltway"], fetch_at("72.00"), verify=lambda e: True)
    inflated = run_request("l", ["voltway"], fetch_at("9999.00"), verify=lambda e: True)
    assert honest.ranked[0].credited == Decimal("72.00")
    assert inflated.ranked[0].credited == Decimal("72.00")
    assert inflated.ranked[0].credited < Decimal("9999.00")


def test_absent_extension_is_absent_not_empty():
    """Plain UCP has no `extensions` key at all. Unguarded access would throw
    on the control merchant, the pane we most need working."""
    def fetch(m, q, *, extension):
        return _body(m, "C-1", "900.00", extension=False)

    run = run_request("laptop", ["citycircuit"], fetch, verify=lambda e: True)
    assert run.ranked[0].records_seen == 0
    assert run.ranked[0].withheld_note
    assert any(s.outcome is Outcome.DEGRADED for s in run.steps)


def test_406_is_a_protocol_outcome_not_a_crash():
    def fetch(m, q, *, extension):
        raise PermissionError("lookup not declared")

    run = run_request("laptop", ["voltway"], fetch)
    assert run.ranked == []
    assert any(s.outcome is Outcome.REFUSED for s in run.steps)


def test_the_flip_is_detected_and_named():
    """A higher shelf price winning on effective cost is the demo. The trace
    must say so rather than leave the UI to notice."""
    def fetch(m, q, *, extension):
        if m == "voltway":
            return _body(m, "VOL-1", "1142.96",
                         [_record("r1", "free_returns", "72.00"),
                          _record("r2", "warranty", "74.50")])
        return _body(m, "CIT-1", "1066.00", extension=False)

    run = run_request("laptop", ["voltway", "citycircuit"], fetch,
                      verify=lambda e: True)
    assert run.winner.merchant == "voltway"
    assert run.winner.effective_cost == Decimal("996.46")
    rank = [s for s in run.steps if s.phase is Phase.RANKING][0]
    assert rank.detail["flipped"] is True


# --- the interpreter, wired (WS-A) ------------------------------------------

R01 = ("A laptop under $1,500 I can return easily if it turns out not to suit "
       "my work, from a brand that actually repairs things")


def test_no_interpreter_is_absent_and_the_utterance_goes_through_unchanged():
    """The ABSENT path still has to work; that is the whole degrade-honestly rule."""
    seen = []

    def fetch(m, q, *, extension):
        seen.append(q)
        return _body(m, "V-1", "1000.00")

    run = run_request(R01, ["voltway"], fetch)
    assert seen == [R01]
    step, = [s for s in run.steps if s.phase is Phase.INTENT]
    assert step.outcome is Outcome.ABSENT
    assert run.constraints == []


def test_the_wired_interpreter_reports_intent_ok_with_the_decoded_clauses():
    def fetch(m, q, *, extension):
        return _body(m, "V-1", "1000.00")

    run = run_request(R01, ["voltway"], fetch, interpret=parse)
    step, = [s for s in run.steps if s.phase is Phase.INTENT]
    assert step.outcome is Outcome.OK
    assert len(run.constraints) == 4
    assert {c["kind"] for c in run.constraints} == {"hard", "soft", "service", "values"}
    # The count of clauses no catalogue attribute can answer, said out loud.
    assert step.detail["by_kind"]["service"] == 1
    assert step.detail["by_kind"]["values"] == 1
    assert "2 of them cannot be answered" in step.summary


def test_the_older_parse_keyword_still_means_the_same_thing():
    """Five branches import this seam; renaming it silently would break them."""
    def fetch(m, q, *, extension):
        return _body(m, "V-1", "1000.00")

    old = run_request(R01, ["voltway"], fetch, parse=parse)
    new = run_request(R01, ["voltway"], fetch, interpret=parse)
    assert old.constraints == new.constraints
    assert [s.outcome for s in old.steps] == [s.outcome for s in new.steps]


def test_the_query_on_the_wire_is_the_decode_not_the_utterance():
    """Sending the raw sentence asks a merchant to keyword-match on "repairs"."""
    seen = []

    def fetch(m, q, *, extension, plan=None):
        seen.append((q, plan))
        return _body(m, "V-1", "1000.00")

    run_request(R01, ["voltway"], fetch, interpret=parse)
    query, plan = seen[0]
    assert R01 not in query
    # The category and the ceiling travel as typed parameters, not as words:
    # catalog.search matches `q` against the title, and no laptop's title
    # contains the word "laptop".
    assert plan == {"category": "laptop", "max_price": "1500"}
    assert query == ""


def test_a_fetcher_that_does_not_want_the_plan_is_never_handed_one():
    """Every existing three-argument fetcher keeps working unchanged."""
    def fetch(m, q, *, extension):
        return _body(m, "V-1", "1000.00")

    run = run_request(R01, ["voltway"], fetch, interpret=parse)
    assert run.winner is not None


def test_service_and_values_clauses_are_never_sent_to_a_merchant():
    """They are the shopper's. A merchant that never sees them cannot price
    against them -- the same reason the shopper policy stays agent-side."""
    seen = []

    def fetch(m, q, *, extension, plan=None):
        seen.append((q, plan))
        return _body(m, "V-1", "1000.00")

    run_request(R01, ["voltway"], fetch, interpret=parse)
    wire = json.dumps(seen[0])
    for phrase in ("return", "repair", "brand"):
        assert phrase not in wire.lower()


def test_policy_from_converts_a_shopper_policy_into_the_dict_the_root_takes():
    """One shopper, defined once, so the demo number is the evaluation number."""
    shopper = ShopperPolicy(
        values_aud={BenefitType.FREE_RETURNS: Decimal("40.00"),
                    BenefitType.TRADE_IN_CREDIT: Decimal("0.00")},
        max_premium_over_cheapest_aud=Decimal("150.00"),
    )
    assert policy_from(shopper) == {"free_returns": Decimal("40.00"),
                                    "trade_in_credit": Decimal("0.00")}


def test_the_default_policy_sentinels_are_uncapped_not_valued():
    """A guard on the comment: 9999 means "accept face value", and against the
    real published ceilings it will over-credit. Callers running on the shipped
    records pass the reference shopper instead."""
    assert DEFAULT_POLICY["trade_in_credit"] == Decimal("9999")
    assert DEFAULT_POLICY["free_returns"] < Decimal("9999")
