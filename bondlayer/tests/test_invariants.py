"""Five judge-readable trust invariants; no catalogue or interpreter required."""

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from bondlayer.records.signing import ES256Signer
from bondlayer.types import BenefitRecord, BenefitType, ShopperPolicy, SignedRecord, Sku
from bondlayer.valuation.effective_cost import DeterministicValuation


@pytest.fixture
def signer():
    return ES256Signer(
        ec.generate_private_key(ec.SECP256R1()),
        key_id="voltway-test-1",
        issuer="voltway.example",
    )


@pytest.fixture
def record():
    return BenefitRecord(
        record_id="returns-1",
        sku_id="VW-LAP-001",
        benefit_type=BenefitType.FREE_RETURNS,
        fact={"days": 60},
        conditions=["Keep proof of purchase"],
        issuer="voltway.example",
        issued_at=datetime(2026, 9, 12, tzinfo=timezone.utc),
        expires_at=None,
        value_ceiling_aud=Decimal("40"),
        source_span="60-day change-of-mind returns.",
    )


@pytest.fixture
def sku():
    return Sku("VW-LAP-001", "Design laptop", "laptop", Decimal("1000"), {})


@pytest.fixture
def policy():
    return ShopperPolicy(
        {BenefitType.FREE_RETURNS: Decimal("25"), BenefitType.SUSTAINABILITY: Decimal("50")},
        max_premium_over_cheapest_aud=Decimal("100"),
    )


def test_tampering_invalidates_signature(signer, record):
    signed = signer.sign(record)
    assert signer.verify(signed)
    tampered = replace(signed, record=replace(record, fact={"days": 61}))
    assert not signer.verify(tampered)


def test_unsigned_record_credits_zero(signer, record, sku, policy):
    unsigned = SignedRecord(record, signature="", key_id="voltway-test-1")
    result = DeterministicValuation(signer).effective_cost(sku, [unsigned], policy)
    assert result.total_credited == Decimal("0")
    assert result.effective_cost == sku.shelf_price
    assert result.credited[0].credited_aud == Decimal("0")
    assert "unverified" in result.credited[0].reason.lower()


def test_inflating_ceiling_to_9999_does_not_change_ranking(signer, record, sku, policy):
    valuation = DeterministicValuation(signer)
    competitor = replace(sku, sku_id="NG-LAP-001", shelf_price=Decimal("990"))
    competitor_cost = valuation.effective_cost(competitor, [], policy)
    normal = valuation.effective_cost(sku, [signer.sign(record)], policy)
    inflated = valuation.effective_cost(
        sku, [signer.sign(replace(record, value_ceiling_aud=Decimal("9999")))], policy,
    )

    # The honest ceiling already covers shopper value. Re-sign the inflation:
    # otherwise this would only prove tamper rejection, not the policy cap.
    def ranking(cost):
        return [item.sku_id for item in sorted(
            [cost, competitor_cost], key=lambda item: (item.effective_cost, item.sku_id),
        )]

    assert normal.total_credited == inflated.total_credited == Decimal("25")
    assert normal.effective_cost == inflated.effective_cost == Decimal("975")
    assert ranking(normal) == ranking(inflated) == [sku.sku_id, competitor.sku_id]


def test_signed_values_claim_is_citable_but_credits_zero(signer, record, sku, policy):
    claim = replace(
        record, benefit_type=BenefitType.SUSTAINABILITY,
        fact={"ewaste_tonnes_fy2026": 412}, value_ceiling_aud=None,
    )
    signed = signer.sign(claim)
    # Verification is the citation gate, not whether the record has a price.
    assert signer.verify(signed)
    assert [item.record.record_id for item in [signed] if signer.verify(item)] == [claim.record_id]
    result = DeterministicValuation(signer).effective_cost(sku, [signed], policy)
    assert result.total_credited == Decimal("0")
    assert result.credited[0].credited_aud == Decimal("0")
    assert "citable" in result.credited[0].reason.lower()


def test_unsigned_greenwashing_is_not_citable_and_credits_zero(signer, record, sku, policy):
    claim = replace(
        record, benefit_type=BenefitType.SUSTAINABILITY,
        fact={"claim": "100% carbon neutral, ethically sourced"},
        value_ceiling_aud=None, source_span=None,
    )
    unsigned = SignedRecord(claim, signature="", key_id="voltway-test-1")
    assert not signer.verify(unsigned)
    assert [item for item in [unsigned] if signer.verify(item)] == []
    result = DeterministicValuation(signer).effective_cost(sku, [unsigned], policy)
    assert result.total_credited == Decimal("0")
    assert result.credited[0].credited_aud == Decimal("0")
    assert "unverified" in result.credited[0].reason.lower()
