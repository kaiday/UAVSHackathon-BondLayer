"""The claims the pitch depends on, as tests — not just assertions in a deck.

Invariant 1: a merchant can NEVER improve its position by inflating a
             declared figure. Value derives from signed FACTS under the
             customer's policy; the declared ceiling only caps.
Invariant 2: a BIGGER unsigned claim costs the merchant MORE. Unverified
             claims are never valued and are penalised in proportion to
             what they ask the agent to believe — under plain
             value-at-zero, lying would be free.

Plus the safety gates the transaction leg depends on: tamper detection,
expiry, key pinning, idempotency without double-discount, and consent.
"""

import pytest

from agentbridge import loyalty
from agentbridge.adapters.mock import MockStoreAdapter
from agentbridge.models import CustomerPolicy, OfferCard
from agentbridge.service import AgentBridgeService

AVA = loyalty.find_member("ava@example.com")


def _credited_total(quote):
    return quote.price_credit_cents + quote.comparison_value_cents


# ------------------------------------------------------------- invariant 1 --

def test_inflating_declared_ceilings_changes_nothing():
    """Double every declared ceiling (and RE-SIGN, as a lying merchant
    would) — the credited totals must not move by a cent."""
    honest = loyalty.value_cards(AVA, 4200, "electronics")

    inflated = []
    for card in loyalty.CARDS:
        c = card.model_copy(deep=True)
        c.value_ceiling_cents *= 2
        if card.signature:  # the merchant signs its own inflated declaration
            loyalty.sign_card(c)
        inflated.append(c)
    puffed = loyalty.value_cards(AVA, 4200, "electronics", cards=inflated)

    assert _credited_total(puffed) == _credited_total(honest)
    assert puffed.payable_total_cents == honest.payable_total_cents


def test_inflating_facts_breaks_the_signature():
    """Facts are the value source, so they are exactly what signing must
    protect: edit a fact without re-signing and the card is worthless."""
    card = next(c for c in loyalty.CARDS if c.card_id == "obc_gold_warranty_12mo")
    tampered = card.model_copy(deep=True)
    tampered.facts = {"extra_warranty_months": 120}
    assert not loyalty.verify_card(tampered)
    quote = loyalty.value_cards(AVA, 4200, "electronics", cards=[tampered])
    assert _credited_total(quote) == 0


def test_unrecognised_facts_derive_zero():
    """A signed card whose facts the customer's policy does not recognise
    is credited nothing — merchants cannot invent new value channels."""
    card = loyalty.sign_card(OfferCard(
        card_id="x_vibes", issuer=loyalty.MERCHANT_ID, benefit_type="vibes",
        description="Immense vibes.", conditions="", facts={"vibes": 9000},
        value_ceiling_cents=99999, affects_price=False,
        issued_at="2026-06-01", expires_at="2027-12-31"))
    quote = loyalty.value_cards(AVA, 4200, "electronics", cards=[card])
    assert _credited_total(quote) == 0


# ------------------------------------------------------------- invariant 2 --

def _unsigned_claim(cents: int) -> OfferCard:
    return OfferCard(
        card_id=f"fake_{cents}", issuer=loyalty.MERCHANT_ID,
        benefit_type="bonus_credit", description=f"${cents / 100:.2f} bonus!!",
        conditions="", facts={"credit_cents": cents},
        value_ceiling_cents=cents, affects_price=True,
        issued_at="2026-09-01", expires_at="2027-12-31", signature=None)


def test_bigger_unsigned_claim_costs_more():
    small = loyalty.value_cards(None, 4200, "electronics",
                                cards=[_unsigned_claim(1000)])
    big = loyalty.value_cards(None, 4200, "electronics",
                              cards=[_unsigned_claim(5000)])
    assert small.price_credit_cents == big.price_credit_cents == 0  # never valued
    assert big.unsigned_penalty_cents > small.unsigned_penalty_cents
    assert big.effective_cost_cents > small.effective_cost_cents
    # ...and worse than claiming nothing at all: lying is not free.
    honest_silence = loyalty.value_cards(None, 4200, "electronics", cards=[])
    assert small.effective_cost_cents > honest_silence.effective_cost_cents


def test_expired_card_is_rejected_without_penalty():
    """Expiry is a lapsed, verifiable promise — rejected, not punished."""
    expired = next(c for c in loyalty.CARDS if c.card_id == "obc_spring_promo")
    quote = loyalty.value_cards(AVA, 4200, "electronics", cards=[expired])
    assert _credited_total(quote) == 0
    assert quote.unsigned_penalty_cents == 0


# ------------------------------------------------------------- key pinning --

def test_keyring_pins_and_refuses_rotation():
    ring = loyalty.KeyRing()
    ring.pin(loyalty.MERCHANT_ID, loyalty.PUBLIC_KEY_HEX)
    signed = next(c for c in loyalty.CARDS if c.signature)
    valid, reason = ring.verify(signed, today="2026-09-02")
    assert valid, reason
    with pytest.raises(ValueError, match="pinned"):
        ring.pin(loyalty.MERCHANT_ID, "ab" * 32)


def test_keyring_unknown_issuer_never_verifies():
    ring = loyalty.KeyRing()
    signed = next(c for c in loyalty.CARDS if c.signature)
    valid, reason = ring.verify(signed, today="2026-09-02")
    assert not valid and "no pinned key" in reason


# -------------------------------------------------------- transaction gates --

def test_idempotent_replay_never_double_discounts():
    svc = AgentBridgeService(MockStoreAdapter())
    svc.identify_member("ava@example.com")
    first = svc.create_order([{"product_id": "prod_charger_gan", "quantity": 1}],
                             "inv-key-1")
    replay = svc.create_order([{"product_id": "prod_charger_gan", "quantity": 1}],
                              "inv-key-1")
    assert replay["order_id"] == first["order_id"]
    assert replay["total_cents"] == first["total_cents"] == 3780
    assert replay["loyalty_credit_cents"] == 420


def test_settlement_charges_the_member_price_once():
    svc = AgentBridgeService(MockStoreAdapter())
    svc.identify_member("ava@example.com")
    order = svc.create_order([{"product_id": "prod_charger_gan", "quantity": 1}],
                             "inv-key-2")
    confirmed = svc.confirm_order(order["order_id"])
    again = svc.confirm_order(order["order_id"])  # replayed confirm: no re-charge
    assert confirmed["total_cents"] == again["total_cents"] == 3780
    assert confirmed["payment_ref"] == again["payment_ref"]


def test_enrolment_requires_consent():
    svc = AgentBridgeService(MockStoreAdapter())
    refused = svc.enroll_member("someone@example.com", consent=False)
    assert "error" in refused
    assert svc.member is None


def test_customer_policy_is_the_shoppers_dial():
    """The same facts value differently under a different policy — the
    number is 'value under a stated policy', never 'true value' (A6)."""
    stingy = CustomerPolicy(warranty_month_value_cents=0,
                            credit_fee_waivers_at_face=False)
    quote = loyalty.value_cards(AVA, 4200, "electronics", policy=stingy)
    assert quote.comparison_value_cents == 0        # warranty+shipping now worth 0
    assert quote.price_credit_cents == 420          # the discount still real
