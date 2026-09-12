"""Invariants for the composition root.

These encode the two rules the module is built on: fail closed, degrade
honestly. They keep the demo truthful while components are missing, which is
the state we are actually in today.
"""

from decimal import Decimal

from bondlayer.agent import Outcome, Phase, run_request


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
