"""Test critical trust invariants for BondLayer signing and valuation.

Per the FPT evaluation spec, these invariants MUST hold:
1. Tampered record fails signature verification
2. Unsigned record credits zero
3. Ceiling caps the credit (attack defense: claim $10k warranty)
"""

import pytest
from datetime import datetime
from round2.valuation.types import BenefitRecord, BenefitType, VerificationKey
from round2.valuation.signing import (
    generate_signing_key_pair,
    create_signed_record,
    verify_benefit_record,
    sign_benefit_record,
)
from round2.valuation.effective_cost import credit_benefit
from round2.valuation.canonical import to_canonical_json, round_trip_test


class TestCanonicalJSON:
    """B2: Canonical JSON serialization - foundation for signing"""

    def test_round_trip(self):
        """Canonical JSON must round-trip deterministically"""
        record = {
            "merchant_id": "voltway",
            "value_aud": 10.50,
            "count": 5,
            "nested": {"z": 1, "a": 2},
        }
        canonical, parsed = round_trip_test(record)

        # Should have sorted keys and compact formatting
        assert canonical == '{"count":5,"merchant_id":"voltway","nested":{"a":2,"z":1},"value_aud":10.5}'
        assert parsed == record

    def test_deterministic_output(self):
        """Same input should always produce same canonical JSON"""
        record = {"z": 1, "a": 2}
        json1 = to_canonical_json(record)
        json2 = to_canonical_json(record)
        assert json1 == json2

        # Keys must be sorted
        assert json1.find('"a"') < json1.find('"z"')


class TestES256Signing:
    """B3: ES256 detached per-record signatures"""

    @pytest.fixture
    def key_pair(self):
        """Generate a test key pair"""
        private_key, jwk_public = generate_signing_key_pair()
        return private_key, jwk_public

    @pytest.fixture
    def unsigned_record(self):
        """Create an unsigned BenefitRecord"""
        return BenefitRecord(
            merchant_id="voltway",
            shopper_id="shopper_123",
            product_id="laptop_pro_16",
            benefit_type=BenefitType.LOYALTY_CREDIT,
            value_aud=50.0,
            value_ceiling_aud=100.0,
            created_at=datetime.now().isoformat(),
            source_span="Loyalty customers: 50 AUD credit",
            merchant_key_id="voltway_2026_key_1",
        )

    def test_sign_and_verify(self, unsigned_record, key_pair):
        """Signed record can be verified"""
        private_key, jwk_public = key_pair

        # Create signed record
        signed_record = create_signed_record(unsigned_record, private_key)

        # Should have signature and canonical JSON
        assert signed_record.signature is not None
        assert signed_record.canonical_json is not None
        assert len(signed_record.signature) > 0

    def test_tampered_record_fails_verify(self, unsigned_record, key_pair):
        """INVARIANT 1: Tampered signature fails verification"""
        private_key, jwk_public = key_pair

        # Sign the record
        signed_record = create_signed_record(unsigned_record, private_key)

        # Create verification key
        verification_key = VerificationKey(
            kid="voltway_2026_key_1",
            kty=jwk_public["kty"],
            crv=jwk_public["crv"],
            x=jwk_public["x"],
            y=jwk_public["y"],
        )

        # Verify original signature works
        assert verify_benefit_record(signed_record, verification_key)

        # Tamper with signature
        tampered = BenefitRecord(
            merchant_id=signed_record.merchant_id,
            shopper_id=signed_record.shopper_id,
            product_id=signed_record.product_id,
            benefit_type=signed_record.benefit_type,
            value_aud=signed_record.value_aud,
            value_ceiling_aud=signed_record.value_ceiling_aud,
            created_at=signed_record.created_at,
            source_span=signed_record.source_span,
            merchant_key_id=signed_record.merchant_key_id,
            signature="TAMPERED_SIGNATURE",
            canonical_json=signed_record.canonical_json,
        )

        # Should fail verification
        assert not verify_benefit_record(tampered, verification_key)

    def test_unsigned_record_credits_zero(self, unsigned_record):
        """INVARIANT 2: Unsigned record credits zero"""
        # Record has no signature
        assert unsigned_record.signature is None

        # Should credit zero
        credited = credit_benefit(unsigned_record)
        assert credited.credited_value == 0.0
        assert not credited.is_verified

    def test_ceiling_caps_credit(self, unsigned_record, key_pair):
        """INVARIANT 3: value_ceiling_aud caps the credited amount"""
        private_key, _ = key_pair

        # Record claims 50 AUD value but has 100 AUD ceiling
        signed_record = create_signed_record(unsigned_record, private_key)
        credited = credit_benefit(signed_record)

        # Should credit min(50, 100) = 50
        assert credited.credited_value == 50.0

        # Now test attacking variant: try to claim $10,000 warranty
        attack_record = BenefitRecord(
            merchant_id="voltway",
            shopper_id="shopper_123",
            product_id="laptop_pro_16",
            benefit_type=BenefitType.WARRANTY_EXTENSION,
            value_aud=10000.0,  # Attack: claim huge value
            value_ceiling_aud=100.0,  # But ceiling is 100
            created_at=datetime.now().isoformat(),
            source_span="Extended warranty coverage",
            merchant_key_id="voltway_2026_key_1",
        )

        signed_attack = create_signed_record(attack_record, private_key)
        credited_attack = credit_benefit(signed_attack)

        # Even signed, should credit only ceiling amount
        assert credited_attack.credited_value == 100.0
        assert credited_attack.is_verified


class TestRecordStates:
    """B7-B9: Three distinct record states with visible crediting"""

    @pytest.fixture
    def key_pair(self):
        private_key, jwk_public = generate_signing_key_pair()
        return private_key, jwk_public

    def test_signed_priced_record(self, key_pair):
        """Signed+priced record: cited and credited"""
        private_key, _ = key_pair

        record = BenefitRecord(
            merchant_id="voltway",
            shopper_id="shopper_123",
            product_id="laptop",
            benefit_type=BenefitType.LOYALTY_CREDIT,
            value_aud=50.0,
            value_ceiling_aud=100.0,
            created_at=datetime.now().isoformat(),
            source_span="Loyalty customers get $50 credit",
            merchant_key_id="voltway_key",
        )

        signed = create_signed_record(record, private_key)
        credited = credit_benefit(signed)

        assert credited.is_verified
        assert credited.credited_value == 50.0
        assert signed.signature is not None
        assert signed.canonical_json is not None

    def test_signed_unpriced_record(self):
        """Signed+unpriced record: cited, visibly $0"""
        # Record with value=0 but is signed
        record = BenefitRecord(
            merchant_id="voltway",
            shopper_id="shopper_123",
            product_id="laptop",
            benefit_type=BenefitType.FREE_SHIPPING,
            value_aud=0.0,  # Zero value
            value_ceiling_aud=0.0,
            created_at=datetime.now().isoformat(),
            source_span="Free shipping offer",
            merchant_key_id="voltway_key",
            signature="mock_sig_0value",
            canonical_json='{"value_aud":0}',
        )

        credited = credit_benefit(record)
        assert credited.credited_value == 0.0
        assert not credited.is_verified  # No valid crypto, but was signed
        assert record.signature is not None

    def test_unsigned_record_displayed_never_cited(self):
        """Unsigned record: displayed, never cited"""
        # Classic "planted" unsigned record
        record = BenefitRecord(
            merchant_id="northgear",
            shopper_id="shopper_123",
            product_id="phone",
            benefit_type=BenefitType.SUSTAINABILITY_CREDIT,
            value_aud=50.0,
            value_ceiling_aud=100.0,
            created_at=datetime.now().isoformat(),
            source_span="Planted: $50 sustainability credit",
            merchant_key_id="northgear_unsigned",
            signature=None,  # No signature
            canonical_json=None,
        )

        credited = credit_benefit(record)
        assert credited.credited_value == 0.0
        assert not credited.is_verified
        assert not record.signature


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
