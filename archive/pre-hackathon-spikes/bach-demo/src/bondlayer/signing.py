"""Ed25519 signing and verification for benefit_value records.

Trust model (D9.8, and its limits): a merchant publishes its public key in its
UCP capability declaration, which the agent already fetches during capability
negotiation. The agent pins the key on first fetch.

This is demo-grade and knowingly so. Fetching a party's key from the party you
are verifying is not a trust root; it stops tampering in transit and stops a
merchant claiming things it did not sign, but it does not stop a merchant that
lies with a valid key. A real deployment needs a registry, a CA, or key
transparency. Recorded in DECISIONS.md "Known weaknesses" rather than papered
over.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from pathlib import Path

from nacl import encoding, exceptions, signing as nacl_signing

from .schema import BenefitValue


class MerchantSigner:
    """Merchant-side. Holds the private key; signs approved records."""

    def __init__(self, merchant_id: str, seed: bytes) -> None:
        self.merchant_id = merchant_id
        self._key = nacl_signing.SigningKey(seed)

    @classmethod
    def from_seed_phrase(cls, merchant_id: str, phrase: str) -> "MerchantSigner":
        """Deterministic key from a phrase, so the demo is reproducible.

        Never do this with a real key.
        """
        seed = phrase.encode("utf-8").ljust(32, b"\0")[:32]
        return cls(merchant_id, seed)

    @property
    def public_key_b64(self) -> str:
        return self._key.verify_key.encode(encoder=encoding.Base64Encoder).decode()

    def sign(self, benefit: BenefitValue) -> BenefitValue:
        if benefit.issuer != self.merchant_id:
            raise ValueError(
                f"refusing to sign: issuer is {benefit.issuer!r}, "
                f"this key belongs to {self.merchant_id!r}"
            )
        unsigned = benefit.model_copy(update={"signature": None})
        sig = self._key.sign(unsigned.signing_payload()).signature
        return benefit.model_copy(
            update={"signature": base64.b64encode(sig).decode()}
        )


class VerificationResult:
    """Why a record was or was not accepted -- surfaced in the UI verbatim."""

    def __init__(self, valid: bool, reason: str) -> None:
        self.valid = valid
        self.reason = reason

    def __bool__(self) -> bool:
        return self.valid

    def __repr__(self) -> str:
        return f"<{'valid' if self.valid else 'INVALID'}: {self.reason}>"


class KeyRing:
    """Agent-side. Public keys only, pinned on first sight."""

    def __init__(self) -> None:
        self._keys: dict[str, nacl_signing.VerifyKey] = {}

    def pin(self, merchant_id: str, public_key_b64: str) -> None:
        key = nacl_signing.VerifyKey(
            public_key_b64.encode(), encoder=encoding.Base64Encoder
        )
        existing = self._keys.get(merchant_id)
        if existing is not None and existing.encode() != key.encode():
            raise ValueError(
                f"key for {merchant_id!r} changed since it was pinned -- refusing"
            )
        self._keys[merchant_id] = key

    def verify(
        self, benefit: BenefitValue, now: datetime | None = None
    ) -> VerificationResult:
        now = now or datetime.now(timezone.utc)

        if benefit.signature is None:
            return VerificationResult(False, "no signature")

        key = self._keys.get(benefit.issuer)
        if key is None:
            return VerificationResult(
                False, f"no pinned key for issuer {benefit.issuer!r}"
            )

        unsigned = benefit.model_copy(update={"signature": None})
        try:
            key.verify(unsigned.signing_payload(), base64.b64decode(benefit.signature))
        except (exceptions.BadSignatureError, ValueError):
            return VerificationResult(
                False, "signature does not match the record contents"
            )

        if benefit.is_expired(now):
            return VerificationResult(
                False, f"expired at {benefit.expires_at.isoformat()}"
            )

        return VerificationResult(True, "signature valid")


def load_or_create_keypair(merchant_id: str, keydir: Path) -> MerchantSigner:
    """Deterministic per-merchant key, persisted so signatures stay stable."""
    keydir.mkdir(parents=True, exist_ok=True)
    seed_file = keydir / f"{merchant_id}.seed"
    if seed_file.exists():
        seed = seed_file.read_bytes()
    else:
        seed = f"bondlayer-demo-key-{merchant_id}".encode().ljust(32, b"\0")[:32]
        seed_file.write_bytes(seed)
    return MerchantSigner(merchant_id, seed)
