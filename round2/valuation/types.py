from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from datetime import datetime


class BenefitType(Enum):
    """Types of benefits that can be offered to shoppers"""
    DISCOUNT = "discount"
    WARRANTY_EXTENSION = "warranty_extension"
    FREE_SHIPPING = "free_shipping"
    LOYALTY_CREDIT = "loyalty_credit"
    SUSTAINABILITY_CREDIT = "sustainability_credit"


@dataclass(frozen=True)
class BenefitRecord:
    """A signed, verifiable benefit offered to a shopper.

    ``terms`` carries the benefit as a **fact**, not as a price: ``warranty_months:
    24``, ``spare_parts_published: true``. That is what most benefits actually are.
    Converting a 24-month warranty into a dollar figure and subtracting it from the
    shelf price invents a number the merchant never offered, so we do not do it --
    the record states what is true and the agent decides what that is worth.

    ``value_aud`` is populated **only** where the benefit genuinely is a cash
    amount (a shipping fee that is waived). Most records leave it at zero, and a
    zero here means "not a monetary benefit", not "worthless".
    """
    merchant_id: str
    shopper_id: str
    product_id: str
    benefit_type: BenefitType
    value_aud: float
    value_ceiling_aud: float
    created_at: str
    source_span: str
    merchant_key_id: str
    terms: dict[str, Any] = field(default_factory=dict)
    signature: Optional[str] = None
    canonical_json: Optional[str] = None

    def __hash__(self):
        return hash((self.merchant_id, self.shopper_id, self.product_id, self.value_aud))


@dataclass(frozen=True)
class CreditedBenefit:
    """The result of evaluating a benefit for a shopper"""
    benefit_record: BenefitRecord
    credited_value: float
    is_verified: bool
    reason: str


@dataclass(frozen=True)
class VerificationKey:
    """A public key for verifying signatures (JWK format)"""
    kid: str  # key id
    kty: str  # "EC"
    crv: str  # "P-256"
    x: str    # base64-url encoded x coordinate
    y: str    # base64-url encoded y coordinate
