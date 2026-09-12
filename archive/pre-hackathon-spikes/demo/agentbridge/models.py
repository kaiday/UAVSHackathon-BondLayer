"""Typed, validated domain models for AgentBridge.

Everything the MCP tools accept or return is defined here as a Pydantic
model, so agents always see a stable, machine-readable schema — the core
of what makes a store "agent-transactable".

Prices are integer cents throughout (no floats near money).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


def cents_to_str(cents: int, currency: str = "USD") -> str:
    """Render integer cents as a human-readable price, e.g. 4450 -> '$44.50'."""
    symbol = {"USD": "$", "EUR": "€", "GBP": "£"}.get(currency, f"{currency} ")
    return f"{symbol}{cents / 100:.2f}"


class Variant(BaseModel):
    """A purchasable variation of a product (e.g. size/colour combo)."""

    variant_id: str
    size: Optional[str] = None
    color: Optional[str] = None
    stock: int = Field(ge=0, description="Units currently available")


class Product(BaseModel):
    """A catalogue entry."""

    product_id: str
    title: str
    description: str
    category: str  # "apparel" | "electronics"
    price_cents: int = Field(gt=0)
    currency: str = "USD"
    variants: list[Variant] = Field(default_factory=list)
    delivery_sla_days: int = Field(gt=0, description="Promised delivery window in days")
    tags: list[str] = Field(default_factory=list)

    @property
    def total_stock(self) -> int:
        return sum(v.stock for v in self.variants)

    @property
    def in_stock(self) -> bool:
        return self.total_stock > 0


class Offer(BaseModel):
    """A concrete, structured quote for buying `quantity` of a product variant.

    This is the object an agent reasons over before ordering: exact price,
    availability confidence, delivery SLA and return terms in one place —
    no free-text parsing required.
    """

    product_id: str
    variant_id: Optional[str] = None
    product_title: str
    quantity: int = Field(gt=0)
    unit_price_cents: int = Field(gt=0)
    total_cents: int = Field(gt=0)
    currency: str = "USD"
    available: bool
    availability_confidence: float = Field(
        ge=0.0, le=1.0,
        description="How confident the store is it can fulfil this quantity (1.0 = reserved stock)",
    )
    delivery_sla_days: int
    return_terms: str
    quoted_at: datetime = Field(default_factory=_now)


class MemberTier(str, Enum):
    BRONZE = "BRONZE"  # any enrolled member
    SILVER = "SILVER"
    GOLD = "GOLD"


_TIER_RANK = {MemberTier.BRONZE: 0, MemberTier.SILVER: 1, MemberTier.GOLD: 2}


def tier_at_least(have: "MemberTier", need: "MemberTier") -> bool:
    return _TIER_RANK[have] >= _TIER_RANK[need]


class Member(BaseModel):
    """A loyalty-program member. The agent identifies (or enrols) one, and
    every subsequent offer is valued under their membership."""

    email: str
    name: str
    tier: MemberTier
    points: int = Field(ge=0)
    member_since: str  # ISO date; display only


class OfferCard(BaseModel):
    """A signed benefit record — the unit of machine-readable loyalty value.

    Facts, not adjectives: what the benefit gives, what it is worth (bounded
    by `value_ceiling_cents`), when it applies (`min_tier`, `category`,
    `expires_at`) and who issued it. The Ed25519 `signature` binds every one
    of those facts to the merchant key, so an agent can verify the *retailer*
    made the claim — an unsigned or tampered card is displayed but NEVER
    valued (see loyalty.value_cards).
    """

    card_id: str
    issuer: str
    benefit_type: str  # "member_price" | "warranty" | "shipping" | "bonus_credit"
    description: str
    conditions: str
    min_tier: Optional[MemberTier] = None  # None = requires no membership
    category: Optional[str] = None         # None = storewide
    # The FACTS are what gets valued — under the customer's policy, never
    # from the merchant's say-so. Recognised keys: percent_off,
    # credit_cents, extra_warranty_months, express_fee_waived_cents.
    facts: dict[str, float] = Field(default_factory=dict)
    # Exact source text used to produce this record. It makes policy-derived
    # benefits citable in the merchant console and evidence ledger.
    source_quote: str = ""
    # The merchant's declared figure is applied ONLY as a cap. Inflating it
    # cannot raise the credited value (enforced by tests/test_invariants.py).
    value_ceiling_cents: int = Field(ge=0)
    affects_price: bool  # True: reduces the settled charge. False: comparison value only.
    issued_at: str   # ISO dates as plain strings so the signed payload is
    expires_at: str  # byte-stable across processes and platforms
    signature: Optional[str] = None  # hex Ed25519 over the canonical card JSON


class CardVerdict(BaseModel):
    """One card's outcome under deterministic valuation: credited or
    rejected, with a machine-readable reason either way."""

    card_id: str
    benefit_type: str
    description: str
    verified: bool   # signature present AND valid for the merchant key
    credited: bool
    reason: str
    credited_value_cents: int = 0
    warning: Optional[str] = None  # set on unverified claims


class CustomerPolicy(BaseModel):
    """The SHOPPER's valuation policy — how facts convert to cents.

    The design never claims a *true* value for a benefit, only a value
    under a stated policy (assumption A6). These defaults are ours, and
    honestly invented; a real agent lets the shopper set them.
    """

    warranty_month_value_cents: int = 25   # an extra warranty month is worth this
    credit_fee_waivers_at_face: bool = True
    # A bigger unsigned claim must COST more, not just count zero —
    # otherwise spamming unverifiable claims is free (invariant 2).
    unsigned_penalty_rate: float = 0.10    # of the claimed ceiling


class LoyaltyQuote(BaseModel):
    """The auditable arithmetic attached to an Offer when a member is known.

    effective_cost is what the agent should rank on: the payable charge
    minus the value (under the customer's policy) of verified non-price
    benefits, plus a penalty proportional to any unverified claims.
    Every number can be recomputed from the verdicts.
    """

    member: Optional[Member] = None
    verdicts: list[CardVerdict] = Field(default_factory=list)
    list_total_cents: int
    price_credit_cents: int = 0        # verified credits that reduce the charge
    payable_total_cents: int           # list - price_credit: what settles
    comparison_value_cents: int = 0    # verified non-price value (warranty etc.)
    unsigned_penalty_cents: int = 0    # proportional cost of unverified claims
    effective_cost_cents: int          # payable - comparison + penalty: rank on THIS
    arithmetic: str = ""               # human-readable derivation


class OrderStatus(str, Enum):
    PENDING = "PENDING"      # created, NO money moved
    CONFIRMED = "CONFIRMED"  # explicitly confirmed; test-mode charge settled
    CANCELLED = "CANCELLED"


class OrderItem(BaseModel):
    """One line of an order request/record."""

    product_id: str
    variant_id: Optional[str] = None
    quantity: int = Field(gt=0)
    unit_price_cents: int = 0  # filled in by the store at order time
    title: str = ""


class Order(BaseModel):
    """An order record. Created PENDING; only confirm_order settles it."""

    order_id: str
    items: list[OrderItem]
    total_cents: int  # the amount that settles — AFTER any loyalty credit
    currency: str = "USD"
    status: OrderStatus = OrderStatus.PENDING
    idempotency_key: str
    # Loyalty: set by the service layer when a member is identified.
    # list_total_cents stays None until loyalty is applied, which is how
    # idempotent replays know not to discount twice.
    member_email: Optional[str] = None
    list_total_cents: Optional[int] = None  # pre-credit total (the shelf price)
    loyalty_credit_cents: int = 0
    payment_ref: Optional[str] = Field(
        default=None,
        description="Test-mode charge reference; set only after confirm_order",
    )
    created_at: datetime = Field(default_factory=_now)
    confirmed_at: Optional[datetime] = None


class Policy(BaseModel):
    """A store policy, returned as structured text an agent can quote."""

    topic: str  # "returns" | "shipping"
    summary: str
    details: str
