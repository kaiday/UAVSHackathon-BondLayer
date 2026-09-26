"""Detached ES256 (P-256/SHA-256), base64url-encoded 64-byte R || S."""

from __future__ import annotations

import base64
from datetime import datetime, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature

from bondlayer.records.canonical import canonical_record
from bondlayer.types import BenefitRecord, SignedRecord


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    if not isinstance(value, str) or not value or any(
        char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for char in value
    ):
        raise ValueError("invalid unpadded base64url")
    raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    if _b64url_encode(raw) != value:
        raise ValueError("noncanonical base64url")
    return raw


class ES256Signer:
    """One trusted issuer/key binding; pass a public key for verification only."""

    def __init__(
        self,
        private_key: ec.EllipticCurvePrivateKey | ec.EllipticCurvePublicKey,
        *,
        key_id: str,
        issuer: str | None = None,
    ) -> None:
        if not isinstance(private_key, (ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey)) or not isinstance(
            private_key.curve, ec.SECP256R1,
        ):
            raise ValueError("ES256 requires an EC P-256 key")
        if not isinstance(key_id, str) or not key_id:
            raise ValueError("key_id must not be empty")
        if issuer is not None and (not isinstance(issuer, str) or not issuer):
            raise ValueError("issuer must not be empty")
        self._key = private_key
        self.key_id = key_id
        self.issuer = issuer

    @classmethod
    def generate(cls, *, key_id: str, issuer: str | None = None) -> ES256Signer:
        return cls(ec.generate_private_key(ec.SECP256R1()), key_id=key_id, issuer=issuer)

    @classmethod
    def from_jwk(cls, jwk: dict[str, str], *, issuer: str) -> ES256Signer:
        """Import a previously trusted UCP public key; does not fetch or trust URLs."""
        if any(jwk.get(key) != value for key, value in {
            "kty": "EC", "crv": "P-256", "alg": "ES256", "use": "sig",
        }.items()) or "d" in jwk:
            raise ValueError("expected an ES256 public signing JWK")
        try:
            x, y = _b64url_decode(jwk["x"]), _b64url_decode(jwk["y"])
            if len(x) != 32 or len(y) != 32:
                raise ValueError("P-256 coordinates must be 32 bytes")
            public_key = ec.EllipticCurvePublicNumbers(
                int.from_bytes(x, "big"), int.from_bytes(y, "big"), ec.SECP256R1(),
            ).public_key()
            return cls(public_key, key_id=jwk["kid"], issuer=issuer)
        except (KeyError, TypeError) as exc:
            raise ValueError("invalid public JWK") from exc

    def sign(self, record: BenefitRecord) -> SignedRecord:
        if not isinstance(self._key, ec.EllipticCurvePrivateKey):
            raise ValueError("signing requires a private key")
        if self.issuer is not None and record.issuer != self.issuer:
            raise ValueError("record issuer does not match signing key issuer")
        der = self._key.sign(canonical_record(record), ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        signature = _b64url_encode(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
        return SignedRecord(record=record, signature=signature, key_id=self.key_id)

    def verify(self, signed: SignedRecord) -> bool:
        """False for untrusted, malformed, tampered, future or expired records."""
        if not isinstance(signed, SignedRecord) or signed.key_id != self.key_id:
            return False
        try:
            payload = canonical_record(signed.record)
            if self.issuer is not None and signed.record.issuer != self.issuer:
                return False
            current = datetime.now(timezone.utc)
            if signed.record.issued_at > current or (
                signed.record.expires_at is not None and signed.record.expires_at <= current
            ):
                return False
            raw = _b64url_decode(signed.signature)
            if len(raw) != 64:
                return False
            der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
            self.public_key.verify(der, payload, ec.ECDSA(hashes.SHA256()))
            return True
        except (InvalidSignature, TypeError, ValueError, OverflowError):
            return False

    @property
    def public_key(self) -> ec.EllipticCurvePublicKey:
        return self._key.public_key() if isinstance(self._key, ec.EllipticCurvePrivateKey) else self._key

    def public_key_pem(self) -> bytes:
        return self.public_key.public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def private_key_pem(self) -> bytes:
        """Persist a merchant-owned key locally; never publish this value."""
        if not isinstance(self._key, ec.EllipticCurvePrivateKey):
            raise ValueError("No private signing key is available")
        return self._key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )

    def public_key_jwk(self) -> dict[str, str]:
        """Export public coordinates for Nguyen to publish in signing_keys[]."""
        numbers = self.public_key.public_numbers()
        return {
            "kty": "EC", "crv": "P-256", "alg": "ES256", "use": "sig",
            "kid": self.key_id, "key_id": self.key_id,
            "x": _b64url_encode(numbers.x.to_bytes(32, "big")),
            "y": _b64url_encode(numbers.y.to_bytes(32, "big")),
        }
