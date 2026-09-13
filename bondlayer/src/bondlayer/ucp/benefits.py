"""Persistent, merchant-owned keys and approved published benefits."""

import json
from dataclasses import replace
from pathlib import Path
from threading import RLock
from uuid import uuid4

from cryptography.hazmat.primitives import serialization

from bondlayer.policy import PolicyOnboardingService, PolicyStore
from bondlayer.policy_ai import OpenAIPolicyConverter
from bondlayer.records import ES256Signer
from bondlayer.records.serialise import signed_to_json
from bondlayer.ucp.storage import validate_id

lock = RLock()


def directory(merchant: str) -> Path:
    from bondlayer.ucp import server
    return server.UPLOADS / "benefits" / validate_id(merchant)


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def published(merchant: str) -> dict:
    path = directory(merchant) / "published.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"records": [], "signing_keys": []}


def restore(merchant: str) -> None:
    from bondlayer.ucp import server
    payload = published(merchant)
    if payload["records"]:
        server._records[merchant] = payload["records"]
        server._merchants[merchant] = replace(server._merchants[merchant], publishes_benefit_extension=True, signs_records=True)


def service(merchant: str) -> PolicyOnboardingService:
    from bondlayer.ucp import server
    profile = server._merchant(merchant)
    issuer = profile.domain or profile.id
    root = directory(merchant)
    with lock:
        root.mkdir(parents=True, exist_ok=True)
        key_path = root / "signing.pem"
        if not key_path.exists():
            signer = ES256Signer.generate(key_id=f"{merchant}-{uuid4().hex[:12]}", issuer=issuer)
            # Private material is only stored below the gitignored upload directory.
            private = signer.private_key_pem()
            key_path.write_bytes(private)
            atomic_json(root / "key.json", signer.public_key_jwk())
        jwk = json.loads((root / "key.json").read_text(encoding="utf-8"))
        signer = ES256Signer(serialization.load_pem_private_key(key_path.read_bytes(), password=None), key_id=jwk["kid"], issuer=issuer)
    converter = OpenAIPolicyConverter(
        issuer, [sku.sku_id for sku in server._catalog[merchant]],
        sorted({sku.category for sku in server._catalog[merchant]}),
    )
    return PolicyOnboardingService(PolicyStore(root / "drafts"), converter, signer)


def publish(merchant: str, onboarding: PolicyOnboardingService) -> dict:
    from bondlayer.ucp import server
    records = [dict(signed_to_json(signed), signed=True) for signed in onboarding.publish(merchant)]
    payload = {"records": records, "signing_keys": [onboarding.signer.public_key_jwk()] if records else []}
    atomic_json(directory(merchant) / "published.json", payload)
    server._records[merchant] = records
    server._merchants[merchant] = replace(server._merchants[merchant], publishes_benefit_extension=bool(records), signs_records=bool(records))
    return {"merchant": merchant, "published": len(records), "records": records}
