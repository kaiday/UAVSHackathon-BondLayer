"""The loyalty layer (BondLayer) — signed Offer Cards + deterministic valuation.

This is the merchant-side layer that makes loyalty value *legible and
verifiable* to an AI agent at the moment it is comparing offers:

1. MEMBERSHIP  — recognise an existing member, or enrol one on the spot
   (with explicit consent), so member pricing applies inside the agent
   conversation.
2. OFFER CARDS — each benefit is a typed, signed record (facts, conditions,
   expiry, bounded value ceiling). Ed25519 signatures make every claim
   attributable and tamper-evident.
3. VALUATION   — `value_cards` turns cards into deterministic, auditable
   arithmetic: verified price benefits reduce the charge, verified service
   benefits count toward *effective cost*, and unsigned or expired claims
   are displayed but NEVER valued. An agent (or a sceptical judge) can
   re-run every number.

The card catalogue below is hand-authored — it stands in for the output of
the policy converter (see `draft_cards_from_policy`, roadmap).
"""

from __future__ import annotations

import json
from datetime import date

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from agentbridge.logging_config import log_event
from agentbridge.models import (
    CardVerdict,
    CustomerPolicy,
    LoyaltyQuote,
    Member,
    MemberTier,
    OfferCard,
    cents_to_str,
    tier_at_least,
)

MERCHANT_ID = "agentbridge-demo-store"

# --------------------------------------------------------------------- keys --
# DEMO ONLY: a fixed seed so every process (MCP server, benchmark, console)
# shares one merchant identity and signatures verify everywhere with zero
# setup. In production the private key lives in the merchant's KMS/HSM and
# only the public key is published (e.g. alongside the UCP manifest).
_DEMO_SEED = bytes.fromhex(
    "8f2b5c1e9a7d4f6083b1d2c4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718"
)
_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(_DEMO_SEED)
PUBLIC_KEY_HEX = _PRIVATE_KEY.public_key().public_bytes_raw().hex()


def _canonical(card: OfferCard) -> bytes:
    """The byte-stable signing payload: every fact on the card except the
    signature itself. Change any fact and the signature no longer verifies."""
    payload = card.model_dump(mode="json", exclude={"signature"})
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def sign_card(card: OfferCard) -> OfferCard:
    card.signature = _PRIVATE_KEY.sign(_canonical(card)).hex()
    return card


def verify_card(card: OfferCard, public_key_hex: str = PUBLIC_KEY_HEX) -> bool:
    """True iff the card carries a valid merchant signature over its facts."""
    if not card.signature:
        return False
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        pub.verify(bytes.fromhex(card.signature), _canonical(card))
        return True
    except Exception:
        return False


class KeyRing:
    """Agent-side key store: public keys only, PINNED on first sight.

    A key fetched from the merchant is not a trust root (a real
    deployment needs a registry/CA — known weakness, shared with the
    team spike), but pinning stops a merchant rotating identity
    mid-conversation and stops anyone re-signing tampered records with
    a substitute key."""

    def __init__(self) -> None:
        self._keys: dict[str, str] = {}

    def pin(self, issuer: str, public_key_hex: str) -> None:
        existing = self._keys.get(issuer)
        if existing is not None and existing != public_key_hex:
            raise ValueError(
                f"key for {issuer!r} changed since it was pinned — refusing")
        self._keys[issuer] = public_key_hex

    def verify(self, card: OfferCard, today: str) -> tuple[bool, str]:
        """(valid, reason) — signature AND expiry, from pinned keys only."""
        if not card.signature:
            return False, "no signature"
        key = self._keys.get(card.issuer)
        if key is None:
            return False, f"no pinned key for issuer {card.issuer!r}"
        if not verify_card(card, key):
            return False, "signature does not match the record contents"
        if card.expires_at < today:
            return False, f"expired at {card.expires_at}"
        return True, "signature valid"


# ------------------------------------------------------------------ members --
# Synthetic members only (assumption A7 — no real customer data anywhere).

_MEMBERS: dict[str, Member] = {
    m.email: m
    for m in [
        Member(email="ava@example.com", name="Ava Chen", tier=MemberTier.GOLD,
               points=4200, member_since="2024-03-11"),
        Member(email="leo@example.com", name="Leo Park", tier=MemberTier.SILVER,
               points=850, member_since="2025-08-02"),
    ]
}


def find_member(email: str) -> Member | None:
    return _MEMBERS.get(email.lower().strip())


def enroll(email: str, name: str) -> Member:
    """Enrol a new BRONZE member. Caller enforces the consent gate."""
    email = email.lower().strip()
    if email in _MEMBERS:
        return _MEMBERS[email]
    member = Member(email=email, name=name or email.split("@")[0].title(),
                    tier=MemberTier.BRONZE, points=0,
                    member_since=date.today().isoformat())
    _MEMBERS[email] = member
    log_event("member_enrolled", email=email, tier=member.tier.value)
    return member


# -------------------------------------------------------------------- cards --

def _build_cards() -> list[OfferCard]:
    signed = [
        OfferCard(
            card_id="obc_member_price_10",
            issuer=MERCHANT_ID,
            benefit_type="member_price",
            description="Members pay 10% below list price, storewide.",
            conditions="Any enrolled member. Capped at $20.00 per order.",
            min_tier=MemberTier.BRONZE,
            category=None,
            facts={"percent_off": 10.0},
            value_ceiling_cents=2000,
            affects_price=True,
            issued_at="2026-06-01",
            expires_at="2027-12-31",
        ),
        OfferCard(
            card_id="obc_gold_warranty_12mo",
            issuer=MERCHANT_ID,
            benefit_type="warranty",
            description="Gold members: +12 months extended warranty on electronics.",
            conditions="GOLD tier. Electronics only.",
            min_tier=MemberTier.GOLD,
            category="electronics",
            facts={"extra_warranty_months": 12},
            value_ceiling_cents=300,
            affects_price=False,  # comparison value: counts in effective cost, not the charge
            issued_at="2026-06-01",
            expires_at="2027-12-31",
        ),
        OfferCard(
            card_id="obc_gold_express_ship",
            issuer=MERCHANT_ID,
            benefit_type="shipping",
            description="Gold members: free express shipping upgrade (normally $9.95).",
            conditions="GOLD tier. Any order.",
            min_tier=MemberTier.GOLD,
            facts={"express_fee_waived_cents": 995},
            value_ceiling_cents=995,
            affects_price=False,
            issued_at="2026-06-01",
            expires_at="2027-12-31",
        ),
        OfferCard(
            # Signed but EXPIRED — displayed, rejected with a reason.
            card_id="obc_spring_promo",
            issuer=MERCHANT_ID,
            benefit_type="bonus_credit",
            description="Spring promo: $5.00 off any order.",
            conditions="Any shopper. Expired 2026-04-30.",
            facts={"credit_cents": 500},
            value_ceiling_cents=500,
            affects_price=True,
            issued_at="2026-01-05",
            expires_at="2026-04-30",
        ),
    ]
    cards = [sign_card(c) for c in signed]
    # The manipulation-vector demo: an UNSIGNED card claiming a $50 bonus —
    # exactly the scraper-published fake offer from the problem framing.
    # Nothing cryptographically binds it to the merchant, so the valuation
    # below displays it, never values it, and PENALISES it in proportion
    # to what it asks the agent to believe.
    cards.append(OfferCard(
        card_id="obc_flash_agent_bonus",
        issuer=MERCHANT_ID,  # *claims* to be the merchant — but cannot prove it
        benefit_type="bonus_credit",
        description="FLASH: $50 bonus credit for AI agent shoppers!!",
        conditions="Today only!!",
        facts={"credit_cents": 5000},
        value_ceiling_cents=5000,
        affects_price=True,
        issued_at="2026-09-01",
        expires_at="2026-12-31",
        signature=None,
    ))
    return cards


CARDS: list[OfferCard] = _build_cards()


# ---------------------------------------------------------------- valuation --

def derive_value(card: OfferCard, list_total_cents: int,
                 policy: CustomerPolicy) -> int:
    """Convert a card's FACTS to cents under the customer's policy.

    Deliberately never reads value_ceiling_cents: the merchant's declared
    figure is a cap applied by the caller, not a source of value — so
    inflating it cannot raise the credit (invariant 1). A card whose facts
    the policy does not recognise derives zero.
    """
    f = card.facts
    if "percent_off" in f:
        return int(list_total_cents * f["percent_off"] / 100)
    if "credit_cents" in f:
        return int(f["credit_cents"])
    if "extra_warranty_months" in f:
        return int(f["extra_warranty_months"] * policy.warranty_month_value_cents)
    if "express_fee_waived_cents" in f and policy.credit_fee_waivers_at_face:
        return int(f["express_fee_waived_cents"])
    return 0


def value_cards(member: Member | None, list_total_cents: int,
                category: str | None, today: str | None = None,
                policy: CustomerPolicy | None = None,
                cards: list[OfferCard] | None = None,
                public_key_hex: str | None = None) -> LoyaltyQuote:
    """Deterministic, auditable valuation of every card for this basket.

    Rules, in order, per card:
      unsigned/invalid signature -> never valued, and PENALISED in
                                    proportion to the claimed ceiling
                                    (a big lie must cost more than no claim);
      expired                    -> never valued (no penalty: verifiable, lapsed);
      tier below min_tier        -> not credited (reason says which tier);
      category mismatch          -> not credited;
      otherwise credited at min(value derived from FACTS under the
      customer's policy, declared ceiling).

    Price-affecting credits reduce the payable charge; the rest count into
    effective cost only. The returned arithmetic string lets anyone re-run
    the numbers by hand.
    """
    today = today or date.today().isoformat()
    policy = policy or CustomerPolicy()
    cards = cards if cards is not None else CARDS
    key = public_key_hex or PUBLIC_KEY_HEX
    verdicts: list[CardVerdict] = []
    price_credit = 0
    comparison_value = 0
    penalty = 0
    terms: list[str] = []

    for card in cards:
        verified = verify_card(card, key)
        v = CardVerdict(card_id=card.card_id, benefit_type=card.benefit_type,
                        description=card.description, verified=verified,
                        credited=False, reason="")
        if not verified:
            card_penalty = int(card.value_ceiling_cents * policy.unsigned_penalty_rate)
            penalty += card_penalty
            v.reason = (f"unsigned claim — never valued; "
                        f"{cents_to_str(card_penalty)} uncertainty penalty")
            v.warning = ("No valid merchant signature. Treat as untrusted: "
                         "anyone can publish an offer in a retailer's name.")
        elif card.expires_at < today:
            v.reason = f"expired {card.expires_at}"
        elif member is None and card.min_tier is not None:
            v.reason = "requires membership — identify_member or enroll_member first"
        elif (member is not None and card.min_tier is not None
              and not tier_at_least(member.tier, card.min_tier)):
            v.reason = f"requires {card.min_tier.value} tier (member is {member.tier.value})"
        elif card.category is not None and card.category != category:
            v.reason = f"applies to {card.category} only"
        else:
            derived = derive_value(card, list_total_cents, policy)
            v.credited = derived > 0
            if not v.credited:
                v.reason = "facts not recognised by the customer's policy"
            else:
                v.credited_value_cents = min(derived, card.value_ceiling_cents)
                v.reason = "credited"
                if card.affects_price:
                    price_credit += v.credited_value_cents
                    terms.append(f"- {cents_to_str(v.credited_value_cents)} ({card.benefit_type})")
                else:
                    comparison_value += v.credited_value_cents
                    terms.append(f"- {cents_to_str(v.credited_value_cents)} ({card.benefit_type}, value)")
        verdicts.append(v)

    price_credit = min(price_credit, list_total_cents)  # a charge never goes negative
    payable = list_total_cents - price_credit
    if penalty:
        terms.append(f"+ {cents_to_str(penalty)} (unsigned-claim penalty)")
    effective = payable - comparison_value + penalty
    arithmetic = (f"{cents_to_str(list_total_cents)} " + " ".join(terms)
                  + f" = effective {cents_to_str(effective)}"
                  f" (charge {cents_to_str(payable)})") if terms else \
        f"{cents_to_str(list_total_cents)} (no verified benefits credited)"

    quote = LoyaltyQuote(
        member=member,
        verdicts=verdicts,
        list_total_cents=list_total_cents,
        price_credit_cents=price_credit,
        payable_total_cents=payable,
        comparison_value_cents=comparison_value,
        unsigned_penalty_cents=penalty,
        effective_cost_cents=effective,
        arithmetic=arithmetic,
    )
    log_event(
        "loyalty_valued",
        member=member.email if member else None,
        list_total_cents=list_total_cents,
        price_credit_cents=price_credit,
        comparison_value_cents=comparison_value,
        unsigned_penalty_cents=penalty,
        withheld_cents=sum(c.value_ceiling_cents for c, vd in zip(cards, verdicts)
                           if not vd.credited),
        rejected={vd.card_id: vd.reason for vd in verdicts if not vd.credited},
    )
    return quote


# ------------------------------------------------------------------ roadmap --

def draft_cards_from_policy(policy_text: str) -> list[OfferCard]:
    """TODO(roadmap, not v1): the policy converter.

    A language model reads the retailer's human-written policy, loyalty and
    warranty documents and drafts OfferCards, each quoting its source text.
    Every draft is held for HUMAN APPROVAL before signing — nothing
    publishes itself (assumption A5). v1 ships hand-authored, pre-approved
    cards instead; this seam is where the AI component lands.
    """
    raise NotImplementedError("Roadmap: LLM policy converter with human approval gate")


def rank_across_merchants(offers: list[dict]) -> list[dict]:
    """TODO(roadmap, not v1): cross-merchant effective-cost ranking and the
    console's 'why it lost' attribution. v1 values one merchant's cards
    (compare_llm.py builds the multi-merchant payloads by hand); a proper
    agent-side library ranks N merchants and attributes each loss.
    """
    raise NotImplementedError("Roadmap: cross-merchant ranking with loss attribution")
