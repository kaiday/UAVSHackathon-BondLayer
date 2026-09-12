"""Arithmetic, applicability and replay checks without an interpreter."""

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from bondlayer.records.signing import ES256Signer
from bondlayer.types import BenefitRecord, BenefitType, ShopperPolicy, Sku
from bondlayer.valuation import DeterministicValuation


@pytest.fixture
def signer():
    return ES256Signer.generate(key_id="voltway-test-1", issuer="voltway.example")


@pytest.fixture
def record():
    return BenefitRecord(
        "returns-1", "VOL-0001", BenefitType.FREE_RETURNS, {"days": 60}, [],
        "voltway.example", datetime(2026, 9, 12, tzinfo=timezone.utc), None, Decimal("40"),
    )


@pytest.fixture
def sku():
    return Sku("VOL-0001", "Laptop", "laptop", Decimal("1000.01"), {"merchant": "voltway"})


@pytest.fixture
def policy():
    return ShopperPolicy({BenefitType.FREE_RETURNS: Decimal("25.01")}, Decimal("100"))


@pytest.fixture
def valuation(signer):
    return DeterministicValuation(signer, merchant_domains={
        "voltway": "voltway.example", "northgear": "northgear.example",
    })


def test_exposes_both_caps_total_and_exact_arithmetic(valuation, signer, record, sku, policy):
    result = valuation.effective_cost(sku, [signer.sign(record)], policy)
    line, = result.credited
    assert result.shelf_price == Decimal("1000.01")
    assert line.merchant_ceiling_aud == Decimal("40")
    assert line.shopper_value_aud == line.credited_aud == Decimal("25.01")
    assert result.total_credited == Decimal("25.01")
    assert result.effective_cost == Decimal("975.00")
    assert "min(" in line.reason


def test_lower_merchant_ceiling_binds(valuation, signer, record, sku, policy):
    result = valuation.effective_cost(sku, [signer.sign(replace(record, value_ceiling_aud=Decimal("10")))], policy)
    assert result.total_credited == Decimal("10")


def test_missing_shopper_value_is_zero(valuation, signer, record, sku, policy):
    result = valuation.effective_cost(sku, [signer.sign(record)], replace(policy, values_aud={}))
    assert result.total_credited == Decimal("0")


def test_duplicate_record_cannot_credit_twice(valuation, signer, record, sku, policy):
    signed = signer.sign(record)
    result = valuation.effective_cost(sku, [signed, signed], policy)
    assert result.total_credited == Decimal("25.01")
    assert "Duplicate" in result.credited[1].reason


def test_foreign_sku_record_has_zero_credit(valuation, signer, record, sku, policy):
    result = valuation.effective_cost(sku, [signer.sign(replace(record, sku_id="VOL-0002"))], policy)
    assert result.total_credited == Decimal("0")


def test_merchant_wide_record_requires_matching_merchant(valuation, signer, record, sku, policy):
    signed = signer.sign(replace(record, sku_id=None))
    assert valuation.effective_cost(sku, [signed], policy).total_credited == Decimal("25.01")
    foreign = replace(sku, attributes={"merchant": "northgear"})
    assert valuation.effective_cost(foreign, [signed], policy).total_credited == Decimal("0")
    unknown = replace(sku, attributes={})
    assert valuation.effective_cost(unknown, [signed], policy).total_credited == Decimal("0")


def test_unknown_merchant_mapping_is_not_trusted(signer, record, sku, policy):
    assert DeterministicValuation(signer).effective_cost(sku, [signer.sign(record)], policy).total_credited == 0


def test_unmet_conditions_withheld_until_explicitly_attested(signer, record, sku, policy):
    record = replace(record, conditions=["member"])
    signed = signer.sign(record)
    kwargs = {"merchant_domains": {"voltway": "voltway.example"}}
    withheld = DeterministicValuation(signer, **kwargs).effective_cost(sku, [signed], policy)
    assert withheld.total_credited == 0
    assert "member" in withheld.credited[0].reason
    eligible = DeterministicValuation(signer, satisfied_conditions=["member"], **kwargs)
    assert eligible.effective_cost(sku, [signed], policy).total_credited == Decimal("25.01")


@pytest.mark.parametrize("bad", [Decimal("NaN"), Decimal("Infinity"), Decimal("-1"), 25.0])
def test_invalid_shopper_values_and_prices_rejected(valuation, record, signer, sku, policy, bad):
    with pytest.raises(ValueError):
        valuation.effective_cost(sku, [signer.sign(record)], replace(policy, values_aud={BenefitType.FREE_RETURNS: bad}))
    with pytest.raises(ValueError):
        valuation.effective_cost(replace(sku, shelf_price=bad), [], policy)


def test_no_benefits_returns_shelf_price(valuation, sku, policy):
    result = valuation.effective_cost(sku, [], policy)
    assert result.credited == [] and result.total_credited == 0
    assert result.effective_cost == sku.shelf_price
