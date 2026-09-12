"""Shared type contracts for BondLayer.

Every component codes against these. Do not change a field without telling the
team in the channel -- five people are importing this module.

Design source: Round 1 Idea Registration, section 5.2 (component table).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol


# --- catalogue -------------------------------------------------------------


@dataclass(frozen=True)
class Sku:
    """One product, after the catalogue adapter has normalised the export."""

    sku_id: str
    title: str
    category: str
    shelf_price: Decimal
    attributes: dict[str, str | int | float | bool]


# --- benefit records -------------------------------------------------------


class BenefitType(str, Enum):
    # Priced benefits -- ontology names per handover section 8 JSON contract
    MEMBER_PRICE = "member_price"
    POINTS_EARN = "points_earn"
    FREE_RETURNS = "free_returns"
    WARRANTY = "warranty"
    TRADE_IN_CREDIT = "trade_in_credit"
    DELIVERY = "delivery"

    # Values claims -- validated, never priced. These answer a VALUES
    # constraint ("only buy from ethical brands") the way a priced benefit
    # answers a SERVICE one. They carry no value_ceiling_aud and contribute
    # nothing to effective cost; their whole job is to be verifiable, so that
    # a signed ethical claim beats unverifiable greenwashing.
    SUSTAINABILITY = "sustainability"
    ETHICAL_SOURCING = "ethical_sourcing"
    DURABILITY = "durability"
    REPAIRABILITY = "repairability"


@dataclass(frozen=True)
class BenefitRecord:
    """A typed claim about non-price value.

    ``value_ceiling_aud`` is the most the merchant asserts this benefit is
    worth. The agent credits min(ceiling, shopper's own policy value), so
    declaring a bigger number cannot buy a better ranking.

    **A ceiling of None means the record is validated but never priced.** That
    is the values-claim case: it can satisfy a VALUES constraint and be cited
    in the justification, and it contributes exactly zero to effective cost.
    Signing makes it attributable and tamper-evident, which is the whole point
    -- a verified durability claim is worth something a marketing adjective is
    not, without ever being converted into dollars.
    """

    record_id: str
    sku_id: str | None  # None = applies to the whole merchant
    benefit_type: BenefitType
    fact: dict[str, str | int | float]  # e.g. {"months": 24}
    conditions: list[str]
    issuer: str  # merchant domain
    issued_at: datetime
    expires_at: datetime | None
    value_ceiling_aud: Decimal | None  # None = validated but never priced
    source_span: str | None = None  # quoted policy text, for the approval gate

    @property
    def is_priced(self) -> bool:
        return self.value_ceiling_aud is not None


@dataclass(frozen=True)
class SignedRecord:
    """A BenefitRecord plus a detached ES256 signature over its canonical JSON.

    Object-level, not transport-level: this survives the response that carried
    it, so an agent can cache, re-verify and cite it.
    """

    record: BenefitRecord
    signature: str  # base64url
    key_id: str  # resolves via signing_keys[] in /.well-known/ucp


# --- intent ----------------------------------------------------------------


class ConstraintKind(str, Enum):
    HARD = "hard"  # "under $1,500"
    SOFT = "soft"  # "good enough for design work"
    SERVICE = "service"  # "I can return it easily"
    VALUES = "values"  # "a brand that actually repairs things"


@dataclass(frozen=True)
class Constraint:
    text: str  # the clause, as the shopper said it
    kind: ConstraintKind


@dataclass(frozen=True)
class ResolvedConstraint:
    constraint: Constraint
    satisfied: bool
    evidence_record_id: str | None  # the record that answers it
    evidence_attribute: str | None  # or the catalogue attribute that does
    note: str  # one line of why -- this is the justification text


@dataclass(frozen=True)
class Proposal:
    """What the merchant returns: not a list of SKUs, a justification."""

    sku: Sku
    resolved: list[ResolvedConstraint]
    unsatisfied: list[Constraint]
    records: list[SignedRecord]


# --- valuation -------------------------------------------------------------


@dataclass(frozen=True)
class CreditedBenefit:
    record_id: str
    benefit_type: BenefitType
    merchant_ceiling_aud: Decimal
    shopper_value_aud: Decimal
    credited_aud: Decimal  # min of the two; 0 if unverified
    reason: str


@dataclass(frozen=True)
class EffectiveCost:
    """Deterministic arithmetic. Never model-generated."""

    sku_id: str
    shelf_price: Decimal
    credited: list[CreditedBenefit]
    effective_cost: Decimal
    total_credited: Decimal = field(default=Decimal("0"))


@dataclass(frozen=True)
class ShopperPolicy:
    """Lives on the agent side. Never sent to a merchant."""

    values_aud: dict[BenefitType, Decimal]
    max_premium_over_cheapest_aud: Decimal


# --- console ---------------------------------------------------------------


@dataclass(frozen=True)
class RequestReport:
    """One agent request, as the merchant's console shows it."""

    request_id: str
    fields_exposed: int
    legible_share: float  # 0..1 of the real offer the wire carried
    value_credited_aud: Decimal
    value_withheld_aud: Decimal
    won: bool
    lost_because: str | None


# --- the seams between components -----------------------------------------


class CatalogAdapter(Protocol):
    def load(self) -> list[Sku]: ...


class PolicyConverter(Protocol):
    def draft(self, document: str) -> list[BenefitRecord]: ...


class Signer(Protocol):
    def sign(self, record: BenefitRecord) -> SignedRecord: ...
    def verify(self, signed: SignedRecord) -> bool: ...


class ConstraintInterpreter(Protocol):
    def parse(self, utterance: str) -> list[Constraint]: ...
    def resolve(
        self, constraints: list[Constraint], skus: list[Sku],
        records: list[SignedRecord],
    ) -> list[Proposal]: ...


class ValuationLibrary(Protocol):
    def effective_cost(
        self, sku: Sku, records: list[SignedRecord], policy: ShopperPolicy,
    ) -> EffectiveCost: ...
