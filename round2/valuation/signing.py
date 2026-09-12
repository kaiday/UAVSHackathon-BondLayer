"""ES256 (P-256/SHA-256) detached signatures for BenefitRecord verification.

Mandatory per Stage 1 spec: ES256 (P-256/SHA-256)
Keys publish in /.well-known/ucp under signing_keys[] in JWK format (RFC 7517)
"""

import hashlib
import base64
from typing import Optional
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.backends import default_backend
from .canonical import to_canonical_json
from .types import BenefitRecord, VerificationKey


def generate_signing_key_pair() -> tuple[ec.EllipticCurvePrivateKey, dict]:
    """Generate a new ES256 key pair.

    Returns:
        Tuple of (private_key, jwk_public_dict)
    """
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())

    public_key = private_key.public_key()
    numbers = public_key.public_numbers()

    # Convert to JWK format
    def int_to_base64url(num: int) -> str:
        """Convert integer to base64url with proper padding for P-256 (32 bytes)."""
        bytes_val = num.to_bytes(32, byteorder='big')
        return base64.urlsafe_b64encode(bytes_val).decode('ascii').rstrip('=')

    jwk = {
        "kty": "EC",
        "crv": "P-256",
        "x": int_to_base64url(numbers.x),
        "y": int_to_base64url(numbers.y),
    }

    return private_key, jwk


def sign_benefit_record(
    record: BenefitRecord,
    private_key: ec.EllipticCurvePrivateKey,
) -> str:
    """Sign a BenefitRecord with ES256.

    Args:
        record: BenefitRecord to sign (must have signature=None)
        private_key: ES256 private key

    Returns:
        Base64url-encoded signature
    """
    if record.signature is not None:
        raise ValueError("Cannot sign an already-signed record")

    # Create signing data with canonical JSON (excluding signature field)
    canonical_json = to_canonical_json({
        "merchant_id": record.merchant_id,
        "shopper_id": record.shopper_id,
        "product_id": record.product_id,
        "benefit_type": record.benefit_type.value,
        "value_aud": record.value_aud,
        "value_ceiling_aud": record.value_ceiling_aud,
        "created_at": record.created_at,
        "source_span": record.source_span,
        "merchant_key_id": record.merchant_key_id,
    })

    # Sign with SHA-256
    signature = private_key.sign(
        canonical_json.encode('utf-8'),
        ec.ECDSA(hashes.SHA256())
    )

    # Encode as base64url
    return base64.urlsafe_b64encode(signature).decode('ascii').rstrip('=')


def verify_benefit_record(
    record: BenefitRecord,
    verification_key: VerificationKey,
) -> bool:
    """Verify an ES256 signature on a BenefitRecord.

    Args:
        record: BenefitRecord with signature
        verification_key: Public key in JWK format

    Returns:
        True if signature is valid, False otherwise
    """
    if not record.signature or not record.canonical_json:
        return False

    try:
        # Reconstruct the public key from JWK
        def base64url_to_int(b64: str) -> int:
            """Convert base64url to integer."""
            b64_padded = b64 + '=' * (4 - len(b64) % 4)
            return int.from_bytes(base64.urlsafe_b64decode(b64_padded), 'big')

        x = base64url_to_int(verification_key.x)
        y = base64url_to_int(verification_key.y)

        public_numbers = ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1())
        public_key = public_numbers.public_key(default_backend())

        # Decode signature
        sig_padded = record.signature + '=' * (4 - len(record.signature) % 4)
        signature_bytes = base64.urlsafe_b64decode(sig_padded)

        # Verify
        public_key.verify(
            signature_bytes,
            record.canonical_json.encode('utf-8'),
            ec.ECDSA(hashes.SHA256())
        )
        return True
    except Exception:
        return False


def create_signed_record(
    unsigned_record: BenefitRecord,
    private_key: ec.EllipticCurvePrivateKey,
) -> BenefitRecord:
    """Create a signed BenefitRecord from an unsigned one.

    Args:
        unsigned_record: BenefitRecord with signature=None
        private_key: ES256 private key

    Returns:
        New BenefitRecord with signature and canonical_json set
    """
    canonical_json = to_canonical_json({
        "merchant_id": unsigned_record.merchant_id,
        "shopper_id": unsigned_record.shopper_id,
        "product_id": unsigned_record.product_id,
        "benefit_type": unsigned_record.benefit_type.value,
        "value_aud": unsigned_record.value_aud,
        "value_ceiling_aud": unsigned_record.value_ceiling_aud,
        "created_at": unsigned_record.created_at,
        "source_span": unsigned_record.source_span,
        "merchant_key_id": unsigned_record.merchant_key_id,
    })

    signature = sign_benefit_record(unsigned_record, private_key)

    # Create new record with signature and canonical JSON
    record_dict = {
        "merchant_id": unsigned_record.merchant_id,
        "shopper_id": unsigned_record.shopper_id,
        "product_id": unsigned_record.product_id,
        "benefit_type": unsigned_record.benefit_type,
        "value_aud": unsigned_record.value_aud,
        "value_ceiling_aud": unsigned_record.value_ceiling_aud,
        "created_at": unsigned_record.created_at,
        "source_span": unsigned_record.source_span,
        "merchant_key_id": unsigned_record.merchant_key_id,
        "signature": signature,
        "canonical_json": canonical_json,
    }

    return BenefitRecord(**record_dict)
