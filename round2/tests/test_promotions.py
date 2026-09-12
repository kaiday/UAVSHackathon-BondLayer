"""Invariants for shopper-scoped promotions.

The promotion layer adds three ways for a record to be worth nothing, and the
value of the layer is that it keeps them apart:

* **unverified**       the signature is absent or wrong -- never was evidence
* **ineligible**       signed, genuine, and fails its own stated condition here
* **shopper_mismatch** signed, genuine, and about somebody else

Collapsing any two of those would let a merchant launder one into another, so
each has a test. A fourth invariant covers the distinction the whole layer turns
on: store credit is not cash, and it must never reach the cash column.

No server is started here. The record filter and the verifier are both pure
functions of a record, a price and a linked shopper, which is the reason they
are testable at all.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROUND2 = Path(__file__).resolve().parents[1]
CHAT_APP = ROUND2 / "chat-app"
for path in (ROUND2, CHAT_APP, CHAT_APP / "src"):
    sys.path.insert(0, str(path))

from agent import ucp_client as uc  # noqa: E402
from merchant.main import _records_for, _resolve_shopper  # noqa: E402
from merchant.seed import Merchant, Sku, load_members  # noqa: E402
from valuation.signing import create_signed_record, generate_signing_key_pair  # noqa: E402
from valuation.types import BenefitRecord, BenefitType  # noqa: E402

KID = "test-key-2026-09"


@pytest.fixture
def key_pair():
    private_key, jwk = generate_signing_key_pair()
    return private_key, uc.VerificationKey(
        kid=KID, kty=jwk["kty"], crv=jwk["crv"], x=jwk["x"], y=jwk["y"]
    )


def _envelope(
    private_key,
    *,
    shopper_id: str,
    benefit_type: BenefitType,
    terms: dict,
    value_aud: float = 0.0,
) -> dict:
    """A signed record on the wire, in the shape the merchant publishes."""
    record = create_signed_record(
        BenefitRecord(
            merchant_id="voltway",
            shopper_id=shopper_id,
            product_id="*",
            benefit_type=benefit_type,
            value_aud=value_aud,
            value_ceiling_aud=value_aud,
            created_at="2026-09-12T09:00:00+00:00",
            source_span="quoted from the merchant's published policy",
            merchant_key_id=KID,
            terms=terms,
        ),
        private_key,
    )
    return {
        "record": {
            "merchant_id": record.merchant_id,
            "shopper_id": record.shopper_id,
            "product_id": record.product_id,
            "benefit_type": record.benefit_type.value,
            "value_aud": record.value_aud,
            "value_ceiling_aud": record.value_ceiling_aud,
            "created_at": record.created_at,
            "source_span": record.source_span,
            "merchant_key_id": record.merchant_key_id,
            "terms": record.terms,
        },
        "signature": record.signature,
        "key_id": KID,
        "canonical_json": record.canonical_json,
        "signed": True,
    }


class TestStoreCreditIsNotCash:
    """The distinction the promotion layer exists to hold."""

    def test_store_credit_gets_a_ceiling_and_no_cash_value(self, key_pair):
        private_key, key = key_pair
        env = _envelope(
            private_key,
            shopper_id="shopper-001",
            benefit_type=BenefitType.LOYALTY_CREDIT,
            terms={"rate_pct": 5, "form": "store_credit", "expires_months": 12},
        )

        v = uc._verify(env, {KID: key}, "voltway", 109.99, "shopper-001")

        assert v.state == "verified_restricted"
        assert v.verified
        # 5% of 109.99 is a real figure, and it is emphatically not cash.
        assert v.ceiling_aud == pytest.approx(5.50)
        assert v.cash_value_aud is None

    def test_cash_discount_at_the_same_rate_does_credit_cash(self, key_pair):
        """Same arithmetic, different ``form`` -- and only the form may decide."""
        private_key, key = key_pair
        env = _envelope(
            private_key,
            shopper_id="shopper-002",
            benefit_type=BenefitType.DISCOUNT,
            terms={"rate_pct": 10, "form": "cash_discount", "min_spend_aud": 0},
        )

        v = uc._verify(env, {KID: key}, "voltway", 109.99, "shopper-002")

        assert v.state == "verified_monetary"
        assert v.cash_value_aud == pytest.approx(11.00)


class TestEligibilityIsCheckedAfterTheSignature:
    """A signature proves who made an offer, never that it applies."""

    def test_signed_offer_below_its_own_minimum_credits_zero(self, key_pair):
        private_key, key = key_pair
        env = _envelope(
            private_key,
            shopper_id="*",
            benefit_type=BenefitType.DISCOUNT,
            terms={"rate_pct": 20, "form": "cash_discount", "min_spend_aud": 150.0},
        )

        v = uc._verify(env, {KID: key}, "northgear", 99.99, "shopper-002")

        assert v.state == "ineligible"
        # Verified, and worth nothing. Both halves matter: it is not dismissed
        # as fake, and it is not credited either.
        assert v.verified
        assert v.cash_value_aud is None
        assert v.ceiling_aud is None
        assert "min_spend_not_met" in v.reason

    def test_the_same_offer_above_the_minimum_credits_cash(self, key_pair):
        private_key, key = key_pair
        env = _envelope(
            private_key,
            shopper_id="*",
            benefit_type=BenefitType.DISCOUNT,
            terms={"rate_pct": 20, "form": "cash_discount", "min_spend_aud": 150.0},
        )

        v = uc._verify(env, {KID: key}, "northgear", 200.00, "shopper-002")

        assert v.state == "verified_monetary"
        assert v.cash_value_aud == pytest.approx(40.00)

    def test_waived_fee_below_its_threshold_is_not_waived(self, key_pair):
        """Free-over-$25 shipping on an $8.99 cable is $8.99 plus postage."""
        private_key, key = key_pair
        env = _envelope(
            private_key,
            shopper_id="*",
            benefit_type=BenefitType.FREE_SHIPPING,
            terms={"free_over_aud": 25.0, "otherwise_flat_rate_aud": 7.95},
            value_aud=7.95,
        )

        v = uc._verify(env, {KID: key}, "voltway", 8.99, None)

        assert v.state == "ineligible"
        assert v.cash_value_aud is None


class TestPromotionsAreNotTransferable:
    def test_another_shoppers_promotion_credits_zero(self, key_pair):
        """``shopper_id`` is inside the signed canonical JSON, so a record cannot
        be lifted onto whoever happens to be holding it."""
        private_key, key = key_pair
        env = _envelope(
            private_key,
            shopper_id="shopper-001",
            benefit_type=BenefitType.DISCOUNT,
            terms={"rate_pct": 10, "form": "cash_discount", "min_spend_aud": 0},
        )

        v = uc._verify(env, {KID: key}, "voltway", 109.99, "shopper-002")

        assert v.state == "shopper_mismatch"
        assert v.cash_value_aud is None
        assert "not transferable" in v.reason

    def test_an_unlinked_agent_cannot_claim_a_named_promotion(self, key_pair):
        private_key, key = key_pair
        env = _envelope(
            private_key,
            shopper_id="shopper-001",
            benefit_type=BenefitType.DISCOUNT,
            terms={"rate_pct": 10, "form": "cash_discount", "min_spend_aud": 0},
        )

        v = uc._verify(env, {KID: key}, "voltway", 109.99, None)

        assert v.state == "shopper_mismatch"
        assert v.cash_value_aud is None


class TestConsentIsStructural:
    """With no linked shopper, named records are never selected in the first
    place. There is no ``if consent:`` for a reviewer to distrust."""

    @pytest.fixture
    def merchant(self):
        return Merchant(
            id="voltway",
            display_name="Voltway",
            domain="voltway.example",
            role="bondlayer",
            publishes_benefit_extension=True,
            signs_records=True,
        )

    @pytest.fixture
    def sku(self):
        return Sku(
            sku_id="VW-107",
            merchant="voltway",
            model_key="kb-mech-tkl",
            title="Mechanical Keyboard TKL",
            category="peripherals",
            shelf_price_aud=109.99,
            gtin=None,
            in_stock=True,
            description="",
        )

    @pytest.fixture(autouse=True)
    def _seeded(self, monkeypatch):
        from merchant import main as merchant_main

        monkeypatch.setitem(
            merchant_main._records,
            "voltway",
            [
                {
                    "record": {
                        "product_id": "*",
                        "shopper_id": "*",
                        "benefit_type": "warranty_extension",
                    }
                },
                {
                    "record": {
                        "product_id": "*",
                        "shopper_id": "shopper-001",
                        "benefit_type": "loyalty_credit",
                    }
                },
            ],
        )

    def test_universal_records_serve_without_a_linked_shopper(self, merchant, sku):
        served = _records_for(merchant, sku, None)
        assert [e["record"]["benefit_type"] for e in served] == ["warranty_extension"]

    def test_named_records_serve_only_to_that_shopper(self, merchant, sku):
        served = _records_for(merchant, sku, "shopper-001")
        assert [e["record"]["benefit_type"] for e in served] == [
            "warranty_extension",
            "loyalty_credit",
        ]

    def test_a_different_shopper_gets_only_the_universal_records(self, merchant, sku):
        served = _records_for(merchant, sku, "shopper-002")
        assert [e["record"]["benefit_type"] for e in served] == ["warranty_extension"]


class TestTheMerchantIsTheAuthorityOnMembership:
    @pytest.fixture(autouse=True)
    def _members(self, monkeypatch):
        from merchant import main as merchant_main

        monkeypatch.setitem(merchant_main._members, "voltway", load_members()["voltway"])

    @pytest.fixture
    def merchant(self):
        return Merchant(
            id="voltway",
            display_name="Voltway",
            domain="voltway.example",
            role="bondlayer",
            publishes_benefit_extension=True,
            signs_records=True,
        )

    def test_a_claimed_id_the_merchant_does_not_know_resolves_to_nobody(self, merchant):
        """An agent cannot talk its way into a loyalty tier."""
        resolved, identity = _resolve_shopper(merchant, "i-am-definitely-a-member")

        assert resolved is None
        assert identity["linked"] is False
        assert identity["reason"] == "not_known_to_this_merchant"

    def test_a_known_member_resolves_with_the_merchants_own_facts(self, merchant):
        resolved, identity = _resolve_shopper(merchant, "shopper-001")

        assert resolved == "shopper-001"
        assert identity["linked"] is True
        assert identity["status"] == "member"
