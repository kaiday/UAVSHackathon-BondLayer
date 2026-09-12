"""The properties the design is actually selling.

Each test corresponds to a claim we would make to a judge. If one of these
fails, the claim is false and must be withdrawn from the pitch -- that is the
point of writing them down.

Run:  .venv/Scripts/python.exe -m pytest tests -q
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bondlayer.agent.policy import CustomerPolicy
from bondlayer.agent.trv import rank, value_offer
from bondlayer.demo_data import (
    GOLD_MEMBER,
    alpine_benefits,
    ridgeway_unsigned_claim,
)
from bondlayer.schema import BenefitType, BenefitValue, Offer
from bondlayer.signing import KeyRing, MerchantSigner
from bondlayer.ucp import capabilities as caps

SIGNER = MerchantSigner.from_seed_phrase("alpine", "bondlayer-demo-key-alpine")


def _keyring() -> KeyRing:
    kr = KeyRing()
    kr.pin("alpine", SIGNER.public_key_b64)
    return kr


def _alpine_offer(price: float = 199.0, inflate: float = 1.0) -> Offer:
    benefits = alpine_benefits(SIGNER, price)
    if inflate != 1.0:
        out = []
        for b in benefits:
            if b.declared_bound_aud is not None:
                b = SIGNER.sign(
                    b.model_copy(
                        update={"declared_bound_aud": b.declared_bound_aud * inflate,
                                "signature": None}
                    )
                )
            out.append(b)
        benefits = out
    return Offer(
        product_id="ALP-STORM-3L", title="Stormline 3L", brand="Alpine Outfitters",
        merchant_id="alpine", merchant_name="Alpine Outfitters", price_aud=price,
        gtin="9312345678907", benefits=benefits, member=GOLD_MEMBER,
    )


# ----------------------------------------------------------------------
# D4 -- the central claim
# ----------------------------------------------------------------------

def test_inflating_a_declared_bound_cannot_help_the_merchant():
    """'A merchant can never improve its own position by inflating a number.'"""
    policy = CustomerPolicy()
    kr = _keyring()

    honest = value_offer(_alpine_offer(inflate=1.0), policy, kr).adjusted_cost_aud
    for factor in (2.0, 10.0, 1000.0):
        inflated = value_offer(_alpine_offer(inflate=factor), policy, kr).adjusted_cost_aud
        assert inflated >= honest, (
            f"inflating bounds by {factor}x lowered adjusted cost "
            f"{honest} -> {inflated}; the ceiling leaked"
        )


def test_understating_a_bound_only_hurts_the_merchant():
    policy = CustomerPolicy()
    kr = _keyring()
    honest = value_offer(_alpine_offer(inflate=1.0), policy, kr).adjusted_cost_aud
    modest = value_offer(_alpine_offer(inflate=0.1), policy, kr).adjusted_cost_aud
    assert modest > honest


# ----------------------------------------------------------------------
# D9.5 -- unverified vs provisional
# ----------------------------------------------------------------------

def test_unsigned_claims_are_never_valued():
    offer = Offer(
        product_id="RW-STORM-3L", title="Stormline 3L", brand="Alpine Outfitters",
        merchant_id="ridgeway", merchant_name="Ridgeway Gear", price_aud=195.0,
        benefits=[ridgeway_unsigned_claim(tampered=False)],
    )
    v = value_offer(offer, CustomerPolicy(), _keyring())
    assert all(l.amount_aud >= 0 for l in v.lines), "an unsigned claim reduced cost"
    assert v.adjusted_cost_aud >= offer.price_aud


def test_a_bigger_lie_costs_more():
    """Escalating an unsigned claim must make the merchant rank worse, not better."""
    kr, policy = _keyring(), CustomerPolicy()

    def cost(tampered: bool) -> float:
        offer = Offer(
            product_id="RW-STORM-3L", title="Stormline 3L", brand="Alpine Outfitters",
            merchant_id="ridgeway", merchant_name="Ridgeway Gear", price_aud=195.0,
            benefits=[ridgeway_unsigned_claim(tampered=tampered)],
        )
        return value_offer(offer, policy, kr).adjusted_cost_aud

    assert cost(True) > cost(False)


def test_penalty_is_capped():
    policy = CustomerPolicy(unverified_penalty_cap_aud=10.0)
    offer = Offer(
        product_id="X", title="X", brand="X", merchant_id="ridgeway",
        merchant_name="Ridgeway Gear", price_aud=195.0,
        benefits=[ridgeway_unsigned_claim(tampered=True)],
    )
    v = value_offer(offer, policy, _keyring())
    assert v.total_penalty_aud <= 10.0


def test_provisional_is_discounted_not_penalised():
    v = value_offer(_alpine_offer(), CustomerPolicy(), _keyring())
    prov = [l for l in v.lines if l.status == "provisional"]
    assert prov, "expected a provisional line"
    assert all(l.amount_aud < 0 for l in prov), "provisional was penalised, not discounted"


# ----------------------------------------------------------------------
# Signing
# ----------------------------------------------------------------------

def test_tampering_with_a_signed_record_invalidates_it():
    signed = alpine_benefits(SIGNER, 199.0)[0]
    kr = _keyring()
    assert kr.verify(signed).valid

    tampered = signed.model_copy(update={"declared_bound_aud": 999.0})
    assert not kr.verify(tampered).valid


def test_expired_records_are_rejected():
    past = datetime.now(timezone.utc) - timedelta(days=1)
    b = SIGNER.sign(
        BenefitValue(
            id="expired", type=BenefitType.free_returns, title="expired offer",
            facts={"return_window_days": 60, "return_shipping_paid": True},
            issuer="alpine", issued_at=past - timedelta(days=30), expires_at=past,
        )
    )
    assert not _keyring().verify(b).valid


def test_a_merchant_cannot_sign_for_another():
    b = BenefitValue(
        id="x", type=BenefitType.free_returns, title="x",
        issuer="peak", issued_at=datetime.now(timezone.utc),
    )
    try:
        SIGNER.sign(b)
    except ValueError:
        return
    raise AssertionError("alpine signed a record issued by peak")


# ----------------------------------------------------------------------
# Eligibility and policy
# ----------------------------------------------------------------------

def test_member_only_benefits_do_not_apply_without_a_member():
    offer = _alpine_offer().model_copy(update={"member": None})
    v = value_offer(offer, CustomerPolicy(), _keyring())
    labels = {l.label for l in v.lines if l.status == "ineligible"}
    assert labels, "member-gated benefits applied with no member linked"


def test_customer_policy_can_override_a_better_adjusted_price():
    """The customer's tolerance wins, not the merchant's arithmetic."""
    offers = [
        _alpine_offer(),
        Offer(product_id="PK", title="Stormline 3L", brand="Alpine Outfitters",
              merchant_id="peak", merchant_name="Peak Supply Co", price_aud=179.0),
    ]
    kr = _keyring()

    generous = rank(offers, CustomerPolicy(max_loyalty_premium_pct=15), kr)
    assert generous[0].offer.merchant_id == "alpine"

    strict = rank(offers, CustomerPolicy(max_loyalty_premium_pct=5), kr)
    assert strict[0].offer.merchant_id == "peak"
    alpine = next(v for v in strict if v.offer.merchant_id == "alpine")
    assert not alpine.eligible


def test_budget_is_a_hard_constraint():
    offers = [_alpine_offer(price=250.0)]
    v = rank(offers, CustomerPolicy(budget_aud=200.0), _keyring())
    assert not v[0].eligible


# ----------------------------------------------------------------------
# D3/D5 -- graceful degradation is what makes the baseline honest
# ----------------------------------------------------------------------

def test_extension_is_pruned_when_the_agent_does_not_declare_it():
    decl = caps.base_declaration("fake-key")
    active = caps.negotiate(decl, [caps.CATALOG_SEARCH, caps.CATALOG_LOOKUP])
    assert caps.BENEFIT_VALUE not in active


def test_extension_is_pruned_when_its_parent_is_absent():
    decl = caps.base_declaration("fake-key")
    active = caps.negotiate(decl, [caps.CATALOG_SEARCH, caps.BENEFIT_VALUE])
    assert caps.BENEFIT_VALUE not in active, "extension survived without its parent"


def test_plain_view_is_identical_to_a_merchant_with_no_extension():
    rich = _alpine_offer()
    plain = rich.without_extension()
    assert plain.benefits == [] and plain.member is None
    assert plain.price_aud == rich.price_aud


# ----------------------------------------------------------------------
# D7 -- the approval gate is the guardrail on the riskiest component
# ----------------------------------------------------------------------

def test_a_fabricated_source_quote_is_caught():
    """The guardrail, tested directly rather than through whatever the recorded
    model happened to do.

    This used to assert that the fixture's drafts contained a hallucination.
    That held only while the fixtures were hand-authored with one planted in.
    Recording against a live model, the model quoted the document faithfully
    and the test failed -- testing the recording, not the check. The check is
    what has to be true.
    """
    from bondlayer.ingest import policy_converter as pc

    doc = "Standard delivery is **$12.95**, and free on orders over $100."

    invented = pc._validate(
        {"source_quote": "Alpine will beat any competitor's price by 10%.",
         "facts": {"discount_pct": 10.0}},
        doc,
    )
    assert any("source quote not found" in w for w in invented), (
        "an invented sentence was not flagged"
    )

    # ...and the check must not fire on markdown emphasis or line wrapping,
    # which is formatting, not fabrication. Before this was fixed, every single
    # draft from the first real recording was rejected for a missing '**'.
    faithful = pc._validate(
        {"source_quote": "Standard delivery is $12.95, and free on orders over $100.",
         "facts": {"free_over_aud": 100.0}},
        doc,
    )
    assert not any("source quote not found" in w for w in faithful), (
        "a faithful quote was rejected over formatting"
    )


def test_policy_converter_flags_drafts_that_need_a_human():
    from bondlayer.ingest import policy_converter as pc

    doc = (Path(__file__).resolve().parents[1]
           / "data" / "merchants" / "alpine" / "policy.md").read_text(encoding="utf-8")
    drafts = pc.draft_from_document(doc, "alpine", allow_network=False)

    assert drafts, "the policy converter produced nothing"
    assert [d for d in drafts if d.warnings], (
        "no draft was flagged; the approval gate has nothing to catch"
    )


def test_only_approved_drafts_are_signed():
    from bondlayer.ingest import policy_converter as pc

    doc = (Path(__file__).resolve().parents[1]
           / "data" / "merchants" / "alpine" / "policy.md").read_text(encoding="utf-8")
    drafts = pc.draft_from_document(doc, "alpine", allow_network=False)
    for d in drafts:
        d.approved = not d.warnings

    signed = pc.sign_approved(drafts, SIGNER)
    assert len(signed) == sum(1 for d in drafts if not d.warnings)
    kr = _keyring()
    assert all(kr.verify(b).valid for b in signed)


def test_an_unapproved_draft_can_never_be_valued():
    """The gate is structural: no signature means no value, whatever it claims."""
    from bondlayer.ingest import policy_converter as pc

    doc = (Path(__file__).resolve().parents[1]
           / "data" / "merchants" / "alpine" / "policy.md").read_text(encoding="utf-8")
    bad = [d for d in pc.draft_from_document(doc, "alpine", allow_network=False)
           if d.warnings]
    offer = Offer(
        product_id="X", title="X", brand="X", merchant_id="alpine",
        merchant_name="Alpine Outfitters", price_aud=199.0,
        benefits=[d.benefit for d in bad], member=GOLD_MEMBER,
    )
    v = value_offer(offer, CustomerPolicy(), _keyring())
    assert v.adjusted_cost_aud >= offer.price_aud, "an unapproved draft reduced cost"
