"""Canonical payload and ES256 wire-format checks."""

import base64
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
import json

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from bondlayer.records.canonical import canonical_record
from bondlayer.records.signing import ES256Signer
from bondlayer.types import BenefitRecord, BenefitType


@pytest.fixture
def record():
    return BenefitRecord(
        "warranty-1", "VW-LAP-001", BenefitType.WARRANTY,
        {"scope": "laptop", "extra_months": 12}, [], "voltway.example",
        datetime(2026, 9, 12, tzinfo=timezone.utc), None, Decimal("40.00"),
        "An extra year of cover.",
    )


@pytest.fixture
def signer():
    return ES256Signer.generate(key_id="voltway-test-1", issuer="voltway.example")


def test_canonical_bytes_ignore_mapping_order_decimal_scale_and_timezone(record):
    equivalent = replace(
        record, fact={"extra_months": 12, "scope": "laptop"},
        value_ceiling_aud=Decimal("4E1"),
        issued_at=datetime(2026, 9, 12, 10, tzinfo=timezone(timedelta(hours=10))),
    )
    assert canonical_record(record) == canonical_record(equivalent)
    payload = json.loads(canonical_record(record))
    assert payload["issued_at"] == "2026-09-12T00:00:00.000000Z"
    assert payload["value_ceiling_aud"] == "40"
    assert "signature" not in payload and "key_id" not in payload
    assert canonical_record(record) == canonical_record(record)


def test_decimal_serialization_never_rounds_with_context(record):
    record = replace(record, value_ceiling_aud=Decimal("123456789.12345678900"))
    with localcontext() as context:
        context.prec = 3
        assert json.loads(canonical_record(record))["value_ceiling_aud"] == "123456789.123456789"


@pytest.mark.parametrize("bad", [Decimal("NaN"), Decimal("Infinity"), Decimal("-1")])
def test_reject_invalid_money(record, signer, bad):
    with pytest.raises(ValueError):
        signer.sign(replace(record, value_ceiling_aud=bad))


def test_reject_naive_datetimes_and_nonfinite_facts(record):
    with pytest.raises(ValueError):
        canonical_record(replace(record, issued_at=datetime(2026, 9, 12)))
    with pytest.raises(ValueError):
        canonical_record(replace(record, fact={"amount": float("nan")}))


def test_detached_es256_is_raw_64_byte_r_s_not_der(record, signer):
    signed = signer.sign(record)
    assert "=" not in signed.signature
    raw = base64.urlsafe_b64decode(signed.signature + "=" * (-len(signed.signature) % 4))
    assert len(raw) == 64
    der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    signer.public_key.verify(der, canonical_record(record), ec.ECDSA(hashes.SHA256()))
    assert signer.verify(signed)


def test_wrong_key_unknown_key_id_and_issuer_fail(record, signer):
    signed = signer.sign(record)
    other = ES256Signer.generate(key_id=signer.key_id, issuer="voltway.example")
    assert not other.verify(signed)
    assert not signer.verify(replace(signed, key_id="unknown"))
    with pytest.raises(ValueError):
        signer.sign(replace(record, issuer="northgear.example"))
    wrong_issuer = ES256Signer(signer.public_key, key_id=signer.key_id, issuer="northgear.example")
    assert not wrong_issuer.verify(signed)


@pytest.mark.parametrize("signature", ["", "!", "a", "AAAA", "A" * 86, "=" * 88])
def test_malformed_signatures_fail_closed(record, signer, signature):
    signed = replace(signer.sign(record), signature=signature)
    assert not signer.verify(signed)


def test_expired_and_future_records_are_not_citable(record, signer):
    expired = replace(
        record, issued_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
        expires_at=datetime(2000, 1, 2, tzinfo=timezone.utc),
    )
    assert not signer.verify(signer.sign(expired))
    future = replace(record, issued_at=datetime(2999, 1, 1, tzinfo=timezone.utc))
    assert not signer.verify(signer.sign(future))


def test_public_jwk_verifies_without_private_key(record, signer):
    jwk = signer.public_key_jwk()
    assert jwk["alg"] == "ES256" and jwk["crv"] == "P-256"
    assert "d" not in jwk
    verifier = ES256Signer.from_jwk(jwk, issuer="voltway.example")
    assert verifier.verify(signer.sign(record))
    with pytest.raises(ValueError, match="private key"):
        verifier.sign(record)


def test_reject_wrong_curve_and_jwk_algorithm(signer):
    with pytest.raises(ValueError):
        ES256Signer(ec.generate_private_key(ec.SECP384R1()), key_id="bad")
    with pytest.raises(ValueError):
        ES256Signer.from_jwk({**signer.public_key_jwk(), "alg": "ES384"}, issuer="voltway.example")
