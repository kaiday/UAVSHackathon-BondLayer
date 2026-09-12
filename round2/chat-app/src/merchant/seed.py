"""Loading the seeded state: manifests, catalogue, published records, keys.

Everything runs from disk with no outbound network call. Venue wifi is shared
by twenty teams and a live call will fail on stage.

Nothing here signs, and nothing here reads a private key. The serving path can
only ever *publish* a public JWK and *serve* a record that was signed offline --
so a fresh clone with no secrets runs the whole demo.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from .capabilities import Capability, merchant_capabilities

DATA = Path(__file__).resolve().parents[2] / "data"
MANIFESTS = DATA / "manifests.json"
CATALOG = DATA / "electronics.csv"
RECORDS = DATA / "records"
KEYS = DATA / "keys"


@dataclass(frozen=True)
class Merchant:
    id: str
    display_name: str
    domain: str
    role: str
    publishes_benefit_extension: bool
    signs_records: bool

    @property
    def capabilities(self) -> list[Capability]:
        return merchant_capabilities(self.publishes_benefit_extension)


@dataclass(frozen=True)
class Sku:
    sku_id: str
    merchant: str
    model_key: str
    title: str
    category: str
    shelf_price_aud: float
    gtin: str | None
    in_stock: bool
    description: str


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


def load_catalog(path: Path = CATALOG) -> dict[str, list[Sku]]:
    """CSV to `Sku`, grouped by merchant."""
    by_merchant: dict[str, list[Sku]] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            sku = Sku(
                sku_id=row["sku_id"],
                merchant=row["merchant"],
                model_key=row["model_key"],
                title=row["title"],
                category=row["category"],
                shelf_price_aud=float(row["shelf_price_aud"]),
                gtin=row["gtin"] or None,
                in_stock=row["in_stock"].strip().lower() == "true",
                description=row["description"],
            )
            by_merchant.setdefault(sku.merchant, []).append(sku)
    return by_merchant


def load_records(merchant_id: str, records_dir: Path = RECORDS) -> list[dict]:
    """Records published by one merchant, or ``[]`` when none are.

    An absent file is a normal state, not an error: the control merchant
    publishes nothing by design.

    **Unsigned records are not rejected here.** A record with no signature
    loads, serves, and is marked ``signed: false`` on the wire so the agent can
    display it and credit it zero. NorthGear's planted claim is exactly this
    case, and it has to reach the screen to lose on it.
    """
    path = records_dir / f"{merchant_id}.signed.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("records", [])


def signing_keys(merchant: Merchant, keys_dir: Path = KEYS) -> list[dict]:
    """Public keys this merchant signs with, in JWK form (RFC 7517).

    Returns ``[]`` when the merchant does not sign, and also when it claims to
    sign but no key has been published. The second case is a real state an agent
    must handle: records arrive but cannot be verified, so they are displayed
    and never valued -- exactly the unsigned path.
    """
    if not merchant.signs_records:
        return []
    path = keys_dir / f"{merchant.id}.pub.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else [payload]
