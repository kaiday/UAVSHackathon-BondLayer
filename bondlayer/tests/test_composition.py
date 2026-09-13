"""Invariants for the composition root.

These encode the two rules the module is built on: fail closed, degrade
honestly. They keep the demo truthful while components are missing, which is
the state we are actually in today.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from bondlayer.adapters.catalog import CsvCatalogAdapter
from bondlayer.agent import DEFAULT_POLICY, Outcome, Phase, policy_from, run_request
from bondlayer.agent.composition import realisable_credit
from bondlayer.interpreter.parser import parse
from bondlayer.types import BenefitType, ShopperPolicy
from bondlayer.valuation import REFERENCE_SHOPPER_POLICY


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
    # The reason is the valuation's own words now, not a restatement of them.
    assert "unverified" in top.citations[0]["why"].lower()
    assert "not citable" in top.citations[0]["why"].lower()


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
    merchant can never be credited more than the shopper thinks it is worth.

    The cap is the reference shopper's $40 free-returns value, which is now the
    default policy. It used to be $72 from a policy dict that lived only in
    this module; one shopper, defined once, is the point of the change.
    """
    cap = DEFAULT_POLICY["free_returns"]
    assert cap == Decimal("40.00")

    def fetch_at(ceiling):
        def fetch(m, q, *, extension):
            return _body(m, "V-1", "1000.00",
                         [_record("r1", "free_returns", ceiling)])
        return fetch

    honest = run_request("l", ["voltway"], fetch_at("72.00"), verify=lambda e: True)
    inflated = run_request("l", ["voltway"], fetch_at("9999.00"), verify=lambda e: True)
    assert honest.ranked[0].credited == cap
    assert inflated.ranked[0].credited == cap
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
    # $1,142.96 shelf, less min($72, $40) returns and min($74.50, $60) warranty
    # under the reference shopper. It was $996.46 when this module credited the
    # merchant's full ceiling; the valuation caps by what the shopper says a
    # benefit is worth, and the valuation is the one that counts.
    assert run.winner.effective_cost == Decimal("1042.96")
    assert run.winner.credited == Decimal("100.00")
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


# --- one valuation, not two (ruling D4/R2) ----------------------------------


def _live_fetch(client):
    """A fetcher over the in-process server, the way the demo runs it."""
    def fetch(merchant, query, *, extension, plan=None):
        params = {"limit": 100}
        if query:
            params["q"] = query
        for key in ("category", "max_price"):
            if (plan or {}).get(key):
                params[key] = plan[key]
        caps = ["dev.ucp.shopping.catalog.search", "dev.ucp.shopping.catalog.lookup"]
        if extension:
            caps.append("org.bondlayer.benefit_value")
        response = client.get(f"/{merchant}/ucp/catalog/search", params=params,
                              headers={"UCP-Agent": ";".join(caps)})
        response.raise_for_status()
        return response.json()
    return fetch


def test_composition_and_the_valuation_agree_to_the_cent_on_r01():
    """The composition root must not re-implement crediting.

    It used to, and the two answers differed by $70 on R01: the inline version
    skipped scope gating, so a laptop earned Voltway's 24-month *appliance*
    cover and its opened-audio returns window. `bondlayer.valuation` is the
    valuation; this asserts the composition root gets the same number out of it
    as a direct call does, listing by listing.
    """
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from bondlayer.records.serialise import load_signed
    from bondlayer.records.signing import ES256Signer
    from bondlayer.ucp.server import app
    from bondlayer.valuation import (
        ATTESTED_CONDITIONS, MERCHANT_DOMAINS, DeterministicValuation,
    )

    root = Path(__file__).resolve().parents[1]
    utterance = json.loads(
        (root / "data" / "eval" / "requests.json").read_text(encoding="utf-8")
    )["requests"][0]["utterance"]

    run = run_request(utterance, list(MERCHANT_DOMAINS), _live_fetch(TestClient(app)),
                      interpret=parse, verify=lambda e: bool(e.get("signed")))
    assert run.ranked, "the server returned nothing to value"

    catalogue = {
        s.sku_id: s
        for s in CsvCatalogAdapter(root / "data" / "catalog" / "electronics.csv").load()
    }
    for entry in run.ranked:
        merchant = entry.merchant
        key = root / "keys" / f"{merchant}.pub.json"
        path = root / "data" / "records" / f"{merchant}.signed.json"
        if not (key.exists() and path.exists()):
            assert entry.credited == Decimal("0")  # publishes nothing, earns nothing
            continue
        jwk, = json.loads(key.read_text(encoding="utf-8"))
        signer = ES256Signer.from_jwk(jwk, issuer=MERCHANT_DOMAINS[merchant])
        direct = DeterministicValuation(
            signer, merchant_domains=MERCHANT_DOMAINS,
            satisfied_conditions=ATTESTED_CONDITIONS,
        ).effective_cost(catalogue[entry.sku_id], load_signed(path),
                         REFERENCE_SHOPPER_POLICY)
        # Agreement to the cent, wherever the shelf price can carry the credit.
        # The only divergence permitted is the ranking floor on a listing worth
        # less than its own benefits, and no laptop in R01 is one.
        assert direct.total_credited <= catalogue[entry.sku_id].shelf_price
        assert entry.credited == direct.total_credited, entry.sku_id
        assert entry.effective_cost == direct.effective_cost, entry.sku_id

    # And the winner is the flip the tests and the evaluation both name.
    assert run.winner.merchant == "voltway"
    assert run.winner.sku_id == "VOL-0031"
    assert run.winner.effective_cost == Decimal("933.01")
    assert run.winner.shelf_price == Decimal("1142.96")
    assert run.winner.shelf_price > min(r.shelf_price for r in run.ranked)


def test_no_listing_can_be_credited_below_zero_on_the_default_policy():
    """A caller who passes nothing must not get a negative effective cost.

    The old default's 9999 sentinels could credit more than the shelf price.
    This walks every listing the server publishes, not just the cheap ones.
    """
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from bondlayer.ucp.server import app
    from bondlayer.valuation import MERCHANT_DOMAINS

    client = TestClient(app)

    def whole_shelf(merchant, query, *, extension):
        """Every listing, not just the ones a title substring matches."""
        caps = ["dev.ucp.shopping.catalog.search", "dev.ucp.shopping.catalog.lookup"]
        if extension:
            caps.append("org.bondlayer.benefit_value")
        response = client.get(f"/{merchant}/ucp/catalog/search",
                              params={"limit": 100},
                              headers={"UCP-Agent": ";".join(caps)})
        response.raise_for_status()
        return response.json()

    run = run_request("anything", list(MERCHANT_DOMAINS), whole_shelf,
                      verify=lambda e: bool(e.get("signed")))
    assert len(run.ranked) > 100, "the sweep did not see the whole catalogue"
    negative = [r for r in run.ranked if r.effective_cost < 0]
    assert not negative, [(r.sku_id, str(r.effective_cost)) for r in negative]
    assert all(r.credited <= r.shelf_price for r in run.ranked)

    # The listings where the floor bit say so out loud rather than silently
    # rounding up: merchant-wide benefits are worth more than a $30 cable.
    floored = [r for r in run.ranked if r.credited == r.shelf_price]
    assert floored, "no listing exercised the floor, so this proves nothing"
    for entry in floored:
        assert entry.withheld_note and "cannot be realised" in entry.withheld_note


def test_realisable_credit_splits_what_a_listing_can_carry_from_what_it_cannot():
    """One rule, called by both the agent and the evaluation runner."""
    # Well within the shelf price: nothing is withheld.
    assert realisable_credit(Decimal("100.00"), Decimal("1142.96")) == (
        Decimal("100.00"), Decimal("0"))
    # Exactly the shelf price: still nothing withheld, and free is not negative.
    assert realisable_credit(Decimal("30.16"), Decimal("30.16")) == (
        Decimal("30.16"), Decimal("0"))
    # Over it: the excess comes back so the caller can say so.
    assert realisable_credit(Decimal("149.95"), Decimal("30.16")) == (
        Decimal("30.16"), Decimal("119.79"))


def test_the_default_policy_is_the_reference_shopper_with_no_sentinels_left():
    """A caller who passes nothing gets the shopper the evaluation is scored on.

    The old default carried 9999 entries meaning "accept the merchant's face
    value, uncapped". Against the real published ceilings -- Voltway's $700
    laptop trade-in and a member price on top -- that summed past the shelf
    price and produced a negative effective cost on R01.
    """
    assert DEFAULT_POLICY == policy_from(REFERENCE_SHOPPER_POLICY)
    assert max(DEFAULT_POLICY.values()) <= Decimal("100")
    assert not [v for v in DEFAULT_POLICY.values() if v >= Decimal("9999")]
    # Trade-in is $0 on purpose: this shopper has no device to trade, which is
    # what neutralises the largest ceiling either merchant publishes.
    assert DEFAULT_POLICY["trade_in_credit"] == Decimal("0.00")


# --- the justification, on the live path (WS-A2) ----------------------------
#
# The resolver always produced the per-constraint reasoning the problem
# statement weighs highest, but only `scripts/eval_run.py` ever called it. These
# pin it to the path the demo and the chat app actually run, and to the one rule
# that makes a citation mean anything: only a record that verified can be one.


def _live_run(utterance, *, extension=True, **kwargs):
    """One request over the real in-process server, as the demo runs it."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from bondlayer.records.serialise import record_from_json
    from bondlayer.records.signing import ES256Signer
    from bondlayer.types import SignedRecord
    from bondlayer.ucp.server import app
    from bondlayer.valuation import MERCHANT_DOMAINS

    client = TestClient(app)

    # Real ES256 against each merchant's published JWK -- not a `signed: true`
    # flag. An unsigned record has to fail *here* for "never cited" to mean
    # anything at all downstream.
    keys: dict = {}
    for merchant in MERCHANT_DOMAINS:
        body = client.get(f"/{merchant}/.well-known/ucp").json()
        domain = body.get("business", {}).get("domain")
        keys[domain] = {j["kid"]: j for j in body.get("signing_keys", []) if j.get("kid")}

    def verify(entry):
        record = entry.get("record") or {}
        jwk = keys.get(record.get("issuer"), {}).get(entry.get("key_id"))
        if jwk is None or not entry.get("signature"):
            return False
        try:
            signer = ES256Signer.from_jwk(jwk, issuer=record["issuer"])
            return signer.verify(SignedRecord(record=record_from_json(record),
                                              signature=entry["signature"],
                                              key_id=entry["key_id"]))
        except (ValueError, KeyError, TypeError):
            return False

    return run_request(utterance, list(MERCHANT_DOMAINS), _live_fetch(client),
                       extension=extension, interpret=parse, verify=verify,
                       policy=policy_from(REFERENCE_SHOPPER_POLICY), **kwargs)


def _cited(offer):
    return {r.evidence_record_id for r in offer.resolved if r.evidence_record_id}


def _markers(offer):
    from bondlayer.interpreter.resolver import UNANSWERED

    return [r for r in offer.resolved if r.note == UNANSWERED]


def test_r01_winner_justifies_every_clause_and_cites_two_records():
    """The gap this closes: the live trace now says WHY, clause by clause.

    Not "here is a cheaper laptop" but "'I can return it easily' is answered by
    vw-returns-60, and 'a brand that actually repairs things' by
    vw-repairability-parts-5y" -- the second signed, worth $0, and cited
    anyway, which is the whole argument for validating a claim without pricing
    it.
    """
    run = _live_run(R01)
    top = run.winner

    assert top.merchant == "voltway"
    assert top.effective_cost == Decimal("933.01")  # the flip is unmoved

    # One ResolvedConstraint per clause the shopper said, and every note is a
    # sentence. A blank justification is worse than none: it looks like one.
    assert len(top.resolved) == len(run.constraints) == 4
    assert all(r.note.strip() for r in top.resolved)

    assert {"vw-returns-60", "vw-repairability-parts-5y"} <= _cited(top)

    by_kind = {r.constraint.kind.value: r for r in top.resolved}
    # HARD is answered by a typed catalogue column, never by a record.
    assert by_kind["hard"].evidence_attribute == "shelf_price"
    assert by_kind["hard"].evidence_record_id is None
    # SOFT ranks and never filters.
    assert by_kind["soft"].satisfied and by_kind["soft"].evidence_record_id is None
    # SERVICE and VALUES are answered by records, and by nothing else.
    assert by_kind["service"].evidence_record_id == "vw-returns-60"
    assert by_kind["values"].evidence_record_id == "vw-repairability-parts-5y"

    assert not top.unsatisfied
    assert any(s.phase is Phase.RESOLVE and s.outcome is Outcome.OK for s in run.steps)


def test_r01_control_answers_neither_clause_and_cites_nothing():
    """Same code path, one capability short: the justification goes honest.

    With the extension undeclared no merchant publishes a record, so both the
    SERVICE and the VALUES clause carry the marker and nothing anywhere is
    cited. This is the half of the demo that proves the other half is real.
    """
    from bondlayer.interpreter.resolver import UNANSWERED

    run = _live_run(R01, extension=False)
    top = run.winner

    assert top.merchant != "voltway"
    assert top.credited == Decimal("0")

    markers = _markers(top)
    assert len(markers) == 2
    assert {m.constraint.kind.value for m in markers} == {"service", "values"}
    assert all(m.note == UNANSWERED and not m.satisfied for m in markers)

    # Nothing is cited, on any offer, anywhere in the run.
    assert not any(_cited(offer) for offer in run.ranked)
    assert {c["kind"] for c in run.unsatisfied} == {"service", "values"}


def test_an_unsigned_record_is_never_cited_even_though_it_is_on_the_wire():
    """R12: NorthGear publishes `ng-sustainability-claim` with no signature.

    It is the one record on the shelf that answers "the most sustainable phone
    you sell", and it is exactly the greenwashing case the proposal is aimed
    at. It must stay visible -- the merchant did publish it -- and it must
    never become evidence. A verified record, or no citation.
    """
    run = _live_run("I want the most sustainable phone you sell")

    seen = {c["record_id"] for offer in run.ranked for c in offer.citations}
    assert "ng-sustainability-claim" in seen, "the record must still be visible"

    for offer in run.ranked:
        assert "ng-sustainability-claim" not in _cited(offer)
        for c in offer.citations:
            if c["record_id"] == "ng-sustainability-claim":
                assert c["cited"] is False and c["credited"] == "0.00"

    # NorthGear's own listings therefore answer the values clause with the
    # marker, not with the unsigned claim.
    northgear = [o for o in run.ranked if o.merchant == "northgear"]
    assert northgear, "northgear must be in the ranking for this to prove anything"
    for offer in northgear:
        values = [r for r in offer.resolved if r.constraint.kind.value == "values"]
        assert values and all(not r.satisfied for r in values)


def test_resolution_attaches_a_reason_and_never_changes_the_answer():
    """The resolver explains the ranking; it must not steer it.

    A resolver that returns nothing must leave the order, the credited amounts
    and the winner exactly as they were -- otherwise the justification is
    quietly moving the arithmetic it is supposed to be describing.
    """
    run = _live_run(R01)
    silent = _live_run(R01, resolve=lambda constraints, skus, records: [])

    assert [r.sku_id for r in silent.ranked] == [r.sku_id for r in run.ranked]
    assert ([r.effective_cost for r in silent.ranked]
            == [r.effective_cost for r in run.ranked])
    assert all(not r.resolved for r in silent.ranked)
    assert any(r.resolved for r in run.ranked)


def test_a_resolver_that_raises_degrades_instead_of_losing_the_run():
    """Degrade honestly: no reason is bad, no ranking is worse."""
    def boom(constraints, skus, records):
        raise RuntimeError("resolver exploded")

    run = _live_run(R01, resolve=boom)

    assert run.winner is not None and run.winner.effective_cost == Decimal("933.01")
    assert any(s.phase is Phase.RESOLVE and s.outcome is Outcome.DEGRADED
               for s in run.steps)
