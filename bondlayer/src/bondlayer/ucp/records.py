"""Loading the signed records this server publishes.

The seam between Bach's branch and mine. He signs offline and commits the
result; this module reads it and the UCP head serves it on the catalogue call.
Nothing here signs, and nothing here needs a private key -- the demo verifies
from a fresh clone with no secrets and no network.

**Unsigned records are not rejected here.** A record with no signature loads,
serves, and is marked ``signed: false`` on the wire so the console can display
it and the valuation can credit it zero. NorthGear's planted greenwashing claim
is exactly this case, and it has to reach the screen to lose on it.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[3] / "data"
RECORDS = DATA / "records"


def _envelope(raw: dict) -> dict:
    """One record as it goes on the wire.

    Mirrors ``SignedRecord`` in ``types.py`` -- ``record`` plus a detached
    ``signature`` and the ``key_id`` that resolves it against ``signing_keys[]``
    in the profile. ``signed`` is derived, never authored: a record is signed
    if and only if it carries both a signature and a key_id.
    """
    record = raw.get("record", raw)
    signature = raw.get("signature")
    key_id = raw.get("key_id") or raw.get("kid")
    return {
        "record": record,
        "signature": signature,
        "key_id": key_id,
        "signed": bool(signature and key_id),
    }


def load_records(merchant_id: str, records_dir: Path = RECORDS) -> list[dict]:
    """Records published by one merchant, or ``[]`` when none are.

    Absent file is a normal state, not an error: the control merchant
    publishes nothing by design, and every merchant publishes nothing until
    Bach's branch lands.
    """
    path = records_dir / f"{merchant_id}.signed.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("records", [])
    return [_envelope(r) for r in payload]


def for_sku(records: list[dict], sku_id: str) -> list[dict]:
    """Records that apply to one listing.

    ``sku_id: null`` means the record applies to the whole merchant -- a
    returns window or a repairability commitment is a property of the retailer,
    not of one laptop -- so those attach to every SKU.
    """
    out = []
    for envelope in records:
        target = envelope["record"].get("sku_id")
        if target is None or target == sku_id:
            out.append(envelope)
    return out
