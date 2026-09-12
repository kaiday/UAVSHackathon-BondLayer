from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
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
    """A signed, verifiable benefit offered to a shopper"""
    merchant_id: str
    shopper_id: str
    product_id: str
    benefit_type: BenefitType
    value_aud: float
    value_ceiling_aud: float
    created_at: str
    source_span: str
    merchant_key_id: str
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
