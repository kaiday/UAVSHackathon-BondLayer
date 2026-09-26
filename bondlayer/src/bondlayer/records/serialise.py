"""Records on disk and on the wire, in exactly the bytes they were signed over.

A detached signature is worth nothing if the record it travelled with does not
round-trip. So the JSON written here is not a second rendering of a record --
it *is* :func:`~bondlayer.records.canonical.canonical_record`'s output, parsed
back into a dict. There is one serialisation, the signed one, and this module
cannot drift from it without the signature failing.

The envelope mirrors ``SignedRecord``::

    {"record": {...}, "signature": "...", "key_id": "voltway-2026-09"}

An unsigned record is published with both fields ``null``. It is not an error
and it is never filtered: NorthGear's greenwashing claim has to arrive in order
to visibly earn nothing. ``ucp/records.py`` derives the wire's ``signed`` flag
from the same two fields, so signed-ness is never authored, here or there.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from bondlayer.records.canonical import canonical_record
from bondlayer.types import BenefitRecord, BenefitType, SignedRecord


def record_to_json(record: BenefitRecord) -> dict:
    """The record as a JSON object, byte-identical to what was signed."""
    return json.loads(canonical_record(record).decode("utf-8"))


def _datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("timestamps must be ISO-8601 strings")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def record_from_json(payload: dict) -> BenefitRecord:
    """Rebuild a record from its published JSON.

    Money arrives as a string, never a float -- ``"12.50"`` is exact and
    ``12.5`` is not, and a signature over a repr is a signature over a guess.
    """
    if not isinstance(payload, dict):
        raise ValueError("a record must be a JSON object")
    ceiling = payload.get("value_ceiling_aud")
    if ceiling is not None and not isinstance(ceiling, str):
        raise ValueError("value_ceiling_aud must be a decimal string or null")
    issued_at = _datetime(payload.get("issued_at"))
    if issued_at is None:
        raise ValueError("issued_at is required")
    return BenefitRecord(
        record_id=payload["record_id"],
        sku_id=payload.get("sku_id"),
        benefit_type=BenefitType(payload["benefit_type"]),
        fact=dict(payload.get("fact") or {}),
        conditions=list(payload.get("conditions") or []),
        issuer=payload["issuer"],
        issued_at=issued_at,
        expires_at=_datetime(payload.get("expires_at")),
        value_ceiling_aud=None if ceiling is None else Decimal(ceiling),
        source_span=payload.get("source_span"),
    )


def signed_to_json(signed: SignedRecord) -> dict:
    """One envelope. Empty signature or key id publishes as ``null``."""
    return {
        "record": record_to_json(signed.record),
        "signature": signed.signature or None,
        "key_id": signed.key_id or None,
    }


def signed_from_json(payload: dict) -> SignedRecord:
    """Read one envelope. A missing signature or key id loads as ``""``.

    An unsigned record is a real published state, not a parse failure: it
    loads, it is offered to the valuation, and it credits nothing there.
    """
    if not isinstance(payload, dict) or "record" not in payload:
        raise ValueError("an envelope must carry a 'record'")
    return SignedRecord(
        record=record_from_json(payload["record"]),
        signature=payload.get("signature") or "",
        key_id=payload.get("key_id") or "",
    )


def dump_signed(path: Path, merchant_id: str, records: list[SignedRecord]) -> None:
    """Write one merchant's published record set."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "merchant": merchant_id,
        "records": [signed_to_json(item) for item in records],
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )


def load_signed(path: Path) -> list[SignedRecord]:
    """Read one merchant's published record set, or ``[]`` when it publishes none.

    An absent file is a normal state: the control merchant publishes nothing by
    design, and that is the status quo the comparison is against.
    """
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("records", [])
    return [signed_from_json(item) for item in payload]
