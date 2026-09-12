"""Total Relationship Value -- deterministic valuation of signed benefits.

This is the UPGRADE path (D8). The demo's primary claim does not depend on it:
an off-the-shelf LLM agent reading BondLayer's structured data already does
better, with no BondLayer code on its side. This module is for agents that
want auditable arithmetic instead of model judgement.

No language model touches any number in this file. Every line of the resulting
ledger is reproducible from the inputs.

The invariant this module exists to enforce (D4):

    A merchant can never improve its own position by inflating a number.

Mechanically: the merchant's declared_bound_aud is applied as
    min(policy_value, declared_bound)
so raising the bound raises a ceiling that is never reached, and lowering it
only costs the merchant. Verified by tests/test_invariants.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..schema import INTRINSIC_VALUE_TYPES, BenefitType, BenefitValue, Offer
from ..signing import KeyRing
from .policy import CustomerPolicy


@dataclass
class LedgerLine:
    """One row of the explanation. Every row states where its number came from."""

    label: str
    amount_aud: float  # negative = reduces adjusted cost
    status: str  # "signed" | "provisional" | "unverified" | "ineligible"
    basis: str  # plain-English derivation, shown in the UI

    @property
    def counted(self) -> bool:
        return self.amount_aud != 0.0


@dataclass
class Valuation:
    offer: Offer
    list_price_aud: float
    lines: list[LedgerLine] = field(default_factory=list)
    excluded_reason: str | None = None

    @property
    def adjusted_cost_aud(self) -> float:
        return round(self.list_price_aud + sum(l.amount_aud for l in self.lines), 2)

    @property
    def total_benefit_aud(self) -> float:
        return round(-sum(l.amount_aud for l in self.lines if l.amount_aud < 0), 2)

    @property
    def total_penalty_aud(self) -> float:
        return round(sum(l.amount_aud for l in self.lines if l.amount_aud > 0), 2)

    @property
    def eligible(self) -> bool:
        return self.excluded_reason is None


# ----------------------------------------------------------------------
# Per-type valuation. Each returns the value TO THE CUSTOMER in AUD,
# derived only from signed facts and the customer's own policy.
# ----------------------------------------------------------------------

def _value_from_facts(
    benefit: BenefitValue, policy: CustomerPolicy, price_aud: float
) -> tuple[float, str]:
    """Return (value_aud, plain-English basis). Never consults declared bounds."""
    f = benefit.facts
    t = benefit.type

    if t is BenefitType.free_returns:
        if not f.get("return_shipping_paid", False):
            return 0.0, "returns are not free; no value counted"
        window = int(f.get("return_window_days", 0))
        if window <= 0:
            return 0.0, "no return window stated"
        # A short window only partly covers the risk of finding out too late.
        coverage = 1.0 if window >= 30 else 0.5
        value = policy.fit_risk_aud * coverage
        basis = (
            f"your fit-risk value ${policy.fit_risk_aud:.2f}"
            + (f" x {coverage:g} for a {window}-day window" if coverage < 1 else "")
        )
        return value, basis

    if t is BenefitType.free_shipping:
        threshold = float(f.get("free_over_aud", 0.0))
        if price_aud < threshold:
            return 0.0, f"order below the ${threshold:.2f} free-shipping threshold"
        return (
            policy.shipping_cost_assumption_aud,
            f"you would otherwise pay ${policy.shipping_cost_assumption_aud:.2f}",
        )

    if t is BenefitType.warranty_extension:
        total = float(f.get("warranty_months", 0))
        standard = float(f.get("statutory_baseline_months", 12))
        extra_years = max(0.0, (total - standard) / 12.0)
        if extra_years == 0:
            return 0.0, "no cover beyond the statutory baseline"
        value = policy.warranty_value_per_year_aud * extra_years
        return value, (
            f"{extra_years:g} extra year(s) x your ${policy.warranty_value_per_year_aud:.2f}/yr"
        )

    if t is BenefitType.member_price:
        # Cross-check the stated dollar discount against the stated percentage.
        # A merchant that inflates one without the other contradicts itself,
        # and we take the lower.
        discount = float(f.get("discount_aud", 0.0))
        pct = f.get("discount_pct")
        if pct is not None:
            implied = price_aud * float(pct) / 100.0
            if implied < discount:
                return implied, (
                    f"{float(pct):g}% of ${price_aud:.2f} = ${implied:.2f} "
                    f"(the stated ${discount:.2f} does not match the stated rate)"
                )
        return discount, f"member price is ${discount:.2f} below list"

    if t is BenefitType.points_earn:
        if not policy.count_points:
            return 0.0, "you chose not to count points"
        # Derived from the merchant's published RATE, not from its declared
        # dollar figure. Deriving from the bound would let the merchant raise
        # its own valuation by raising the bound -- exactly what D4 forbids,
        # and exactly what test_inflating_a_declared_bound_cannot_help_the_
        # merchant caught when this was written the other way round.
        per_aud = float(f.get("points_per_aud", 0) or 0)
        per_redeem = float(f.get("redemption_points_per_aud", 0) or 0)
        if per_aud <= 0 or per_redeem <= 0:
            return 0.0, "points rate not published in a machine-readable form"
        earned_aud = price_aud * per_aud / per_redeem
        value = earned_aud * policy.points_confidence
        return value, (
            f"{per_aud:g} pts/$ on ${price_aud:.2f} redeemed at {per_redeem:g} pts/$1 "
            f"= ${earned_aud:.2f}, x your {policy.points_confidence:.0%} confidence "
            "after breakage"
        )

    if t is BenefitType.tier_progression:
        if not policy.count_tier_progression:
            return 0.0, "you chose not to count tier progression"
        # No fact can establish what a tier is worth to you, so this is the
        # customer's number, discounted for being a forecast. The merchant's
        # declared bound can only cap it.
        value = policy.tier_progression_value_aud * policy.provisional_confidence
        return value, (
            f"your ${policy.tier_progression_value_aud:.2f} value for reaching "
            f"{f.get('next_tier', 'the next tier')} x your "
            f"{policy.provisional_confidence:.0%} confidence -- depends on future spend"
        )

    if t is BenefitType.retention_offer:
        # Defined in the ontology, produced by nothing here (D6).
        discount = float(f.get("discount_aud", 0.0))
        return discount, "retention offer"

    return 0.0, "unknown benefit type; not valued"


def value_offer(
    offer: Offer,
    policy: CustomerPolicy,
    keyring: KeyRing,
    now: datetime | None = None,
) -> Valuation:
    """Compute one merchant's adjusted relationship cost."""
    now = now or datetime.now(timezone.utc)
    v = Valuation(offer=offer, list_price_aud=offer.price_aud)

    unverified_notional = 0.0

    for benefit in offer.benefits:
        check = keyring.verify(benefit, now=now)

        # --- unmet conditions: displayed, not valued, not penalised ---
        unmet = benefit.conditions.unmet_by(offer.member, offer.price_aud)
        if unmet:
            v.lines.append(
                LedgerLine(
                    label=benefit.title,
                    amount_aud=0.0,
                    status="ineligible",
                    basis="; ".join(unmet),
                )
            )
            continue

        raw_value, basis = _value_from_facts(benefit, policy, offer.price_aud)

        if not check.valid:
            # D9.5: unverified claims are NEVER valued, and are penalised in
            # proportion to what they ask you to believe. Under a plain
            # value-at-zero rule a merchant spamming unverifiable claims ends
            # up exactly where an honest merchant who claims nothing ends up.
            unverified_notional += raw_value
            v.lines.append(
                LedgerLine(
                    label=benefit.title,
                    amount_aud=0.0,
                    status="unverified",
                    basis=f"{check.reason} -- displayed, never valued",
                )
            )
            continue

        # D4: the merchant's declared number is a CEILING, never a floor.
        if benefit.type in INTRINSIC_VALUE_TYPES and benefit.declared_bound_aud is not None:
            capped = min(raw_value, benefit.declared_bound_aud)
        else:
            capped = raw_value
            if benefit.declared_bound_aud is not None:
                capped = min(raw_value, benefit.declared_bound_aud)

        if capped < raw_value:
            basis += f"; capped at the merchant's declared ${benefit.declared_bound_aud:.2f}"

        if capped == 0.0:
            v.lines.append(
                LedgerLine(benefit.title, 0.0, "signed", basis)
            )
            continue

        v.lines.append(
            LedgerLine(
                label=benefit.title,
                amount_aud=-round(capped, 2),
                status="provisional" if benefit.is_provisional else "signed",
                basis=basis,
            )
        )

    if unverified_notional > 0:
        penalty = min(
            unverified_notional * policy.unverified_penalty_rate,
            policy.unverified_penalty_cap_aud,
        )
        v.lines.append(
            LedgerLine(
                label="Uncertainty penalty",
                amount_aud=round(penalty, 2),
                status="unverified",
                basis=(
                    f"{policy.unverified_penalty_rate:.0%} of ${unverified_notional:.2f} "
                    "in claims this merchant asks you to take on faith"
                ),
            )
        )

    return v


def rank(
    offers: list[Offer],
    policy: CustomerPolicy,
    keyring: KeyRing,
    now: datetime | None = None,
) -> list[Valuation]:
    """Rank by adjusted cost, after applying the customer's hard constraints."""
    valuations = [value_offer(o, policy, keyring, now=now) for o in offers]
    if not valuations:
        return []

    cheapest_list = min(v.list_price_aud for v in valuations)

    for v in valuations:
        if policy.budget_aud is not None and v.list_price_aud > policy.budget_aud:
            v.excluded_reason = (
                f"list price ${v.list_price_aud:.2f} is over your "
                f"${policy.budget_aud:.2f} budget"
            )
            continue
        premium = (v.list_price_aud - cheapest_list) / cheapest_list * 100
        if premium > policy.max_loyalty_premium_pct:
            v.excluded_reason = (
                f"{premium:.1f}% above the cheapest list price, over your "
                f"{policy.max_loyalty_premium_pct:.0f}% tolerance"
            )

    return sorted(
        valuations,
        key=lambda v: (not v.eligible, v.adjusted_cost_aud),
    )
