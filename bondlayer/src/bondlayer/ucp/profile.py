"""``/.well-known/ucp`` -- the profile an agent reads before anything else.

This is the key discovery mechanism the entire verification story depends on.
If ``signing_keys[]`` is not reachable and correct, every signature we publish
is unverifiable and the pitch is an assertion rather than a demonstration.

**We publish Bach's key; we never generate one.** A signing key minted by the
serving layer would prove nothing -- the point is that the records were signed
by the merchant's own key, out of band, and that any agent can check them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from bondlayer.ucp.capabilities import (
    BENEFIT_VALUE,
    BENEFIT_VALUE_EXTENDS,
    INTENT_MATCH,
    INTENT_MATCH_EXTENDS,
    Capability,
    merchant_capabilities,
)

DATA = Path(__file__).resolve().parents[3] / "data"
MANIFESTS = DATA / "policies" / "manifests.json"
#: Bach writes public keys here. Gitignored (`keys/*.pem`); absent until his
#: branch lands, which must degrade visibly rather than crash.
KEYS = DATA.parent / "keys"

PROTOCOL_VERSION = "2026-04-08"
BENEFIT_SPEC_URL = "https://bondlayer.example/spec/benefit_value"
BENEFIT_SCHEMA_URL = "https://bondlayer.example/schemas/benefit_value.json"
INTENT_SPEC_URL = "https://bondlayer.example/spec/intent_match"
INTENT_SCHEMA_URL = "https://bondlayer.example/schemas/intent_match.json"


@dataclass(frozen=True)
class Merchant:
    """One merchant profile, straight from the manifest."""

    id: str
    display_name: str
    domain: str
    role: str
    publishes_benefit_extension: bool
    signs_records: bool

    @property
    def capabilities(self) -> list[Capability]:
        return merchant_capabilities(self.publishes_benefit_extension)


def load_merchants(path: Path = MANIFESTS) -> dict[str, Merchant]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        mid: Merchant(
            id=mid,
            display_name=m["display_name"],
            domain=m["domain"],
            role=m["role"],
            publishes_benefit_extension=m["publishes_benefit_extension"],
            signs_records=m["signs_records"],
        )
        for mid, m in payload["merchants"].items()
    }


def signing_keys(merchant: Merchant, keys_dir: Path = KEYS) -> list[dict]:
    """Public keys this merchant signs with, as published by Bach.

    Returns ``[]`` when the merchant does not sign, and also when it claims to
    sign but no key has been published yet. The second case is a real state an
    agent must handle: records arrive but cannot be verified, so they are
    displayed and never valued -- exactly the unsigned path.
    """
    if not merchant.signs_records:
        return []
    path = keys_dir / f"{merchant.id}.pub.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else [payload]


def build_profile(merchant: Merchant, keys_dir: Path = KEYS) -> dict:
    """The document served at ``/{merchant}/.well-known/ucp``.

    Extension declaration follows the spec's own shape: reverse-domain name,
    a ``version``, the parent capabilities it ``extends``, and where its spec
    and schema live.
    """
    caps = {
        c.name: [{"version": v} for v in c.versions]
        for c in merchant.capabilities
        if not c.is_extension
    }
    extensions: dict[str, list[dict]] = {}
    if merchant.publishes_benefit_extension:
        extensions[BENEFIT_VALUE] = [
            {
                "version": "draft",
                "extends": list(BENEFIT_VALUE_EXTENDS),
                "spec": BENEFIT_SPEC_URL,
                "schema": BENEFIT_SCHEMA_URL,
            }
        ]
        extensions[INTENT_MATCH] = [
            {
                "version": "draft",
                "extends": list(INTENT_MATCH_EXTENDS),
                "spec": INTENT_SPEC_URL,
                "schema": INTENT_SCHEMA_URL,
            }
        ]

    return {
        "protocol_version": PROTOCOL_VERSION,
        "business": {
            "id": merchant.id,
            "name": merchant.display_name,
            "domain": merchant.domain,
        },
        "capabilities": caps,
        "extensions": extensions,
        "signing_keys": signing_keys(merchant, keys_dir),
    }
