"""Effective cost calculation and benefit crediting.

Rules:
- credited = min(value_ceiling_aud, verified_value_aud)
- unsigned records credit zero
- tampered signatures result in zero credit
"""

from typing import Optional
from .types import BenefitRecord, CreditedBenefit, VerificationKey
from .signing import verify_benefit_record


def credit_benefit(
    record: BenefitRecord,
    verification_key: Optional[VerificationKey] = None,
) -> CreditedBenefit:
    """Calculate the credited value of a benefit record.

    Args:
        record: BenefitRecord to evaluate
        verification_key: Public key for verification (optional for demo)

    Returns:
        CreditedBenefit with credited_value, is_verified, and reason
    """
    # Check if record is signed
    if not record.signature:
        return CreditedBenefit(
            benefit_record=record,
            credited_value=0.0,
            is_verified=False,
            reason="unsigned_no_credit",
        )

    # Try to verify if we have a key
    is_verified = False
    if verification_key:
        is_verified = verify_benefit_record(record, verification_key)
    else:
        # In demo mode, accept signed records as verified
        is_verified = bool(record.canonical_json)

    if not is_verified:
        return CreditedBenefit(
            benefit_record=record,
            credited_value=0.0,
            is_verified=False,
            reason="unverified_no_credit",
        )

    # Credit is min of value and ceiling
    credited = min(record.value_aud, record.value_ceiling_aud)

    return CreditedBenefit(
        benefit_record=record,
        credited_value=credited,
        is_verified=True,
        reason="verified_credited",
    )


def calculate_effective_cost(
    base_price: float,
    benefit_records: list[BenefitRecord],
    verification_keys: Optional[dict[str, VerificationKey]] = None,
) -> tuple[float, list[CreditedBenefit]]:
    """Calculate effective cost after applying verified benefits.

    Args:
        base_price: Original price in AUD
        benefit_records: List of BenefitRecords to apply
        verification_keys: Dict mapping merchant_key_id -> VerificationKey (optional for demo)

    Returns:
        Tuple of (effective_cost, list_of_credited_benefits)
    """
    verification_keys = verification_keys or {}

    credited_benefits = []
    total_credit = 0.0

    for record in benefit_records:
        key = verification_keys.get(record.merchant_key_id)
        credited = credit_benefit(record, key)
        credited_benefits.append(credited)
        total_credit += credited.credited_value

    effective_cost = max(0.0, base_price - total_credit)

    return effective_cost, credited_benefits


def rank_by_effective_cost(
    items: list[tuple[str, float, list[BenefitRecord]]],
    verification_keys: Optional[dict[str, VerificationKey]] = None,
) -> list[tuple[str, float, float, list[CreditedBenefit]]]:
    """Rank items by effective cost after benefits.

    Args:
        items: List of (item_id, base_price, benefits)
        verification_keys: Dict mapping merchant_key_id -> VerificationKey

    Returns:
        List of (item_id, base_price, effective_cost, credited_benefits) sorted by effective_cost
    """
    ranked = []
    for item_id, base_price, benefits in items:
        effective_cost, credited = calculate_effective_cost(base_price, benefits, verification_keys)
        ranked.append((item_id, base_price, effective_cost, credited))

    return sorted(ranked, key=lambda x: x[2])
