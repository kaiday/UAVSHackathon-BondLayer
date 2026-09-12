"""org.bondlayer.benefit_value — schema v0.1.

Design constraints this schema is built under (see DECISIONS.md):

D4  A merchant signs verifiable FACTS. It may declare a bounded amount only
    where money is intrinsic to the benefit (a points rate, a discount).
    The declared bound is a CEILING, never a floor -- so inflating it can
    never improve the merchant's position.

D8  The published data must be self-describing. An LLM that has never seen
    this schema must make sense of a record from field names and units
    alone. That rules out codes, enums-as-integers and clever compression:
    `return_window_days: 60` earns its place, `rw: 60` does not.

D9.5 Two distinct kinds of doubt, deliberately not merged:
      - unverified: signature missing or invalid -> penalised (never valued)
      - provisional: signed, but a forecast or conditional on future
        behaviour -> confidence-weighted (discounted, not penalised)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

EXTENSION_NAME = "org.bondlayer.benefit_value"
EXTENSION_VERSION = "2026-08-30"


class BenefitType(str, Enum):
    """Ontology v0.1 (D9.6).

    `retention_offer` is defined but produced by nothing in this build -- the
    Retention Decision Engine was cut (D6). Defining it now costs nothing and
    keeps that deferred work purely additive.
    """

    points_earn = "points_earn"
    member_price = "member_price"
    free_returns = "free_returns"
    free_shipping = "free_shipping"
    warranty_extension = "warranty_extension"
    tier_progression = "tier_progression"
    retention_offer = "retention_offer"


#: Types where the money is intrinsic to the benefit and cannot be derived
#: from customer preferences alone -- only the merchant knows its own points
#: rate or discount. These are the only types allowed to carry a declared
#: bound (D4).
INTRINSIC_VALUE_TYPES = {
    BenefitType.points_earn,
    BenefitType.member_price,
    BenefitType.tier_progression,
    BenefitType.retention_offer,
}

#: Types whose value is a forecast or depends on future customer behaviour.
#: Signed, but confidence-weighted rather than taken at face value (D9.5).
PROVISIONAL_TYPES = {BenefitType.tier_progression}


class Conditions(BaseModel):
    """Eligibility, published so an agent can test it BEFORE checkout.

    This is the part UCP cannot express today: its loyalty extension evaluates
    conditions merchant-side at checkout, by which point the comparison is
    already over (docs/ucp-findings.md, finding 3).
    """

    requires_membership: bool = False
    requires_tier: str | None = None
    min_order_aud: float = 0.0
    excludes_sale_items: bool = False

    def unmet_by(self, member: "MemberContext | None", price_aud: float) -> list[str]:
        """Return human-readable reasons this benefit does not apply."""
        reasons: list[str] = []
        if self.requires_membership and member is None:
            reasons.append("requires membership; no member linked")
        if self.requires_tier is not None:
            if member is None:
                reasons.append(f"requires {self.requires_tier} tier; no member linked")
            elif member.tier.lower() != self.requires_tier.lower():
                reasons.append(
                    f"requires {self.requires_tier} tier; member is {member.tier}"
                )
        if price_aud < self.min_order_aud:
            reasons.append(f"requires order of at least ${self.min_order_aud:.2f}")
        return reasons


class BenefitValue(BaseModel):
    """One typed, bounded, conditional, expiring, signed claim."""

    id: str
    type: BenefitType
    title: str = Field(description="Human-readable; displayed, never valued.")

    facts: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Verifiable statements about the benefit, in explicit units. "
            "This is what the agent values under the customer's own policy."
        ),
    )

    declared_bound_aud: float | None = Field(
        default=None,
        description=(
            "CEILING on what this benefit may be valued at, in AUD. Only "
            "meaningful for intrinsic-value types. Raising it can never raise "
            "the computed value (D4)."
        ),
    )

    conditions: Conditions = Field(default_factory=Conditions)

    issuer: str = Field(description="Merchant id; must match the signing key.")
    issued_at: datetime
    expires_at: datetime | None = None

    signature: str | None = Field(
        default=None,
        description="Ed25519 over the canonical form. Absent => never valued.",
    )

    # ------------------------------------------------------------------
    # Canonical form. Signed and verified over exactly this, so that field
    # ordering, whitespace and float formatting cannot change the digest.
    # ------------------------------------------------------------------
    def signing_payload(self) -> bytes:
        body = self.model_dump(mode="json", exclude={"signature"})
        return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()

    @property
    def is_provisional(self) -> bool:
        return self.type in PROVISIONAL_TYPES

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        now = now or datetime.now(timezone.utc)
        return now > self.expires_at


class MemberContext(BaseModel):
    """Member state surfaced at CATALOG time.

    UCP puts this in the checkout response (dev.uip.shopping.loyalty). We
    surface it during comparison instead, because that is where it can change
    an outcome (D3). Only present when a member is linked via
    dev.ucp.common.identity_linking -- with no linked member the catalog
    response is byte-identical to plain UCP.

    Balances follow the UCP loyalty convention: integers in minor units.
    """

    member_id: str
    program_name: str
    tier: str
    points_active: int = 0
    points_pending: int = 0
    units_to_next_tier: int | None = None
    next_tier: str | None = None

    @property
    def points_total(self) -> int:
        return self.points_active + self.points_pending


class Offer(BaseModel):
    """A product offer as the agent sees it.

    Plain-UCP fields only, plus the extension block. With the extension pruned
    during capability negotiation, `benefits` and `member` are absent and this
    is an ordinary UCP catalog entry -- which is the demo's honest "before"
    state (D5).
    """

    product_id: str
    title: str
    brand: str
    merchant_id: str
    merchant_name: str
    price_aud: float
    currency: str = "AUD"
    availability: str = "in_stock"
    gtin: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    # --- org.bondlayer.benefit_value extension block ---
    benefits: list[BenefitValue] = Field(default_factory=list)
    member: MemberContext | None = None

    def without_extension(self) -> "Offer":
        """Plain UCP view -- what an agent that did not negotiate us sees."""
        return self.model_copy(update={"benefits": [], "member": None})
