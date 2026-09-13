"""Author, sign and publish the benefit records the merchants serve.

This is the Day 1 work plan's 14:30 fallback taken deliberately rather than in a
panic: a **curated** record set, authored against the policy prose, so that the
interpreter and the comparison have something real to run on whether or not the
converter lands. Every record below carries the sentence it came from in
``source_span``, which is the same thing the converter's approval gate would
show a human before publishing.

    python scripts/sign_records.py

Writes, relative to ``bondlayer/``:

* ``keys/<merchant>.pem``      -- the private signing key. **Gitignored.**
* ``keys/<merchant>.pub.json`` -- the public JWK, published in the profile's
  ``signing_keys[]``. Committed, because a fresh clone has to verify with no
  network and no secrets.
* ``data/records/<merchant>.signed.json`` -- what the UCP head serves.

Re-running is safe: an existing private key is reused rather than replaced, so
signatures stay stable across runs. Delete a ``.pem`` to rotate a key, and
re-run to re-sign everything under the new one.

Two things this script must never do, and does not:

* **Sign NorthGear's sustainability claim.** It is published unsigned, on
  purpose, and the demo depends on it arriving and earning nothing.
* **Sign anything the prose does not say.** Every ceiling is an assertion the
  merchant is making; the shopper's own policy caps what any of them is worth,
  so an inflated ceiling buys nothing but embarrassment in Q&A.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402

from bondlayer.records.serialise import dump_signed  # noqa: E402
from bondlayer.records.signing import ES256Signer  # noqa: E402
from bondlayer.types import BenefitRecord, BenefitType, SignedRecord  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
KEYS = ROOT / "keys"
RECORDS = ROOT / "data" / "records"

#: Authored inside the competition window, with the policy documents open.
ISSUED_AT = datetime(2026, 9, 12, tzinfo=timezone.utc)
#: Voltway's terms are "effective 1 July 2026"; a year is the honest term for a
#: published policy, and an expiry an agent can see beats one it has to assume.
EXPIRES_AT = datetime(2027, 7, 1, tzinfo=timezone.utc)


def record(
    record_id: str,
    issuer: str,
    benefit_type: BenefitType,
    fact: dict,
    source_span: str | None,
    *,
    ceiling: str | None = None,
    conditions: tuple[str, ...] = (),
    sku_id: str | None = None,
) -> BenefitRecord:
    """One claim. ``ceiling=None`` means validated but never priced."""
    return BenefitRecord(
        record_id=record_id,
        sku_id=sku_id,
        benefit_type=benefit_type,
        fact=fact,
        conditions=list(conditions),
        issuer=issuer,
        issued_at=ISSUED_AT,
        expires_at=EXPIRES_AT,
        value_ceiling_aud=None if ceiling is None else Decimal(ceiling),
        source_span=source_span,
    )


VOLTWAY = "voltway.example"
NORTHGEAR = "northgear.example"


# --- Voltway ---------------------------------------------------------------
#
# Nine priced records and three values claims, matching
# data/policies/manifests.json -> voltway.expect_records.
#
# Ceilings are what Voltway asserts each benefit is worth, derived from its own
# prose: the returns ceiling is the $14.95 return shipping a member does not pay
# plus the option value of thirty days more window than the market norm; the
# points and member-price ceilings are the caps on a rate, so they are stated as
# caps rather than as a figure that only holds for one basket.

VOLTWAY_RECORDS = [
    record(
        "vw-returns-60", VOLTWAY, BenefitType.FREE_RETURNS,
        {"days": 60},
        "We accept change-of-mind returns on most items for 60 days from the "
        "delivery date, provided the item is in resaleable condition with its "
        "original packaging. ... Return shipping is free for Voltway Circle members.",
        ceiling="45.00", conditions=("resaleable", "Original packaging retained"),
    ),
    record(
        "vw-returns-opened-audio-14", VOLTWAY, BenefitType.FREE_RETURNS,
        {"days": 14, "scope": "opened audio"},
        "Change-of-mind returns on opened audio products are limited to 14 days "
        "for hygiene reasons.",
        ceiling="10.00", conditions=("resaleable",),
    ),
    record(
        "vw-warranty-laptop-phone-12", VOLTWAY, BenefitType.WARRANTY,
        {"extra_months": 12, "scope": "laptop,phone"},
        "All laptops and phones carry the manufacturer warranty plus an additional "
        "12 months of Voltway Cover at no extra charge.",
        ceiling="60.00",
    ),
    record(
        "vw-warranty-appliance-24", VOLTWAY, BenefitType.WARRANTY,
        {"extra_months": 24, "scope": "appliance"},
        "Appliances carry 24 months of Voltway Cover in addition to the "
        "manufacturer term.",
        ceiling="110.00",
    ),
    record(
        "vw-points-4x", VOLTWAY, BenefitType.POINTS_EARN,
        {"points_per_dollar": 4, "cents_per_point": 1},
        "Members earn 4 points per dollar spent. Points are worth 1 cent each on "
        "redemption, so 4 points per dollar is an effective 4% return.",
        ceiling="60.00", conditions=("member",),
    ),
    record(
        "vw-member-price-5", VOLTWAY, BenefitType.MEMBER_PRICE,
        {"discount_pct": 5},
        "Members receive member pricing on selected lines, typically 5% below the "
        "shelf price, and the discount is applied automatically at checkout.",
        ceiling="75.00",
        conditions=("member", "Does not stack with clearance pricing"),
    ),
    record(
        "vw-tradein-laptop-700", VOLTWAY, BenefitType.TRADE_IN_CREDIT,
        {"cap_aud": 700, "scope": "laptop"},
        "Trade-in credit is assessed on condition and model, and is capped at "
        "$450 for phones and $700 for laptops.",
        ceiling="700.00", conditions=("trade_in_device",),
    ),
    record(
        "vw-tradein-phone-450", VOLTWAY, BenefitType.TRADE_IN_CREDIT,
        {"cap_aud": 450, "scope": "phone"},
        "Trade-in credit is assessed on condition and model, and is capped at "
        "$450 for phones and $700 for laptops.",
        ceiling="450.00", conditions=("trade_in_device",),
    ),
    record(
        "vw-delivery-free-99", VOLTWAY, BenefitType.DELIVERY,
        {"free_over_aud": 99},
        "Standard delivery is free on orders over $99. Below that threshold, "
        "standard delivery is $9.95.",
        ceiling="9.95", conditions=("order_over_99",),
    ),
    # --- values claims: validated, never priced ---------------------------
    record(
        "vw-repairability-parts-5y", VOLTWAY, BenefitType.REPAIRABILITY,
        {"parts_years_after_eol": 5, "publishes_repair_pricing": True},
        "We publish repair pricing for every product we sell. We stock spare "
        "parts for a minimum of five years after a product line is discontinued.",
    ),
    record(
        "vw-sustainability-assured-fy2026", VOLTWAY, BenefitType.SUSTAINABILITY,
        {"assured_emissions_statement": True, "ewaste_tonnes_fy2026": 412},
        "We publish an annual emissions statement, independently assured by a "
        "third party ... In FY2026 we recovered 412 tonnes of e-waste through "
        "that scheme.",
    ),
    record(
        "vw-durability-oow-quote", VOLTWAY, BenefitType.DURABILITY,
        {"out_of_warranty_repair_quoted": True},
        "We will quote on out-of-warranty repairs for any product we have sold, "
        "regardless of age.",
    ),
]


# --- NorthGear -------------------------------------------------------------
#
# A real competitor, not a strawman: its 45-day returns window genuinely beats
# the control's 30, and it signs five priced records. What it cannot do is put a
# signature on an adjective.

NORTHGEAR_RECORDS = [
    record(
        "ng-returns-45", NORTHGEAR, BenefitType.FREE_RETURNS,
        {"days": 45},
        "We offer a 45 day change of mind returns window on all products, with "
        "free return shipping on orders over $200.",
        ceiling="30.00",
    ),
    record(
        "ng-warranty-6", NORTHGEAR, BenefitType.WARRANTY,
        {"extra_months": 6, "scope": "laptop,appliance"},
        "NorthGear adds 6 months of extended cover on appliances and laptops at "
        "no charge.",
        ceiling="30.00",
    ),
    record(
        "ng-points-2x", NORTHGEAR, BenefitType.POINTS_EARN,
        {"points_per_dollar": 2, "cents_per_point": 1},
        "Plus members pay $49 per year. In return they receive ... 2 points per "
        "dollar (redeemable at 1 cent per point).",
        ceiling="30.00", conditions=("paid_member",),
    ),
    record(
        "ng-tradein-phone-300", NORTHGEAR, BenefitType.TRADE_IN_CREDIT,
        {"cap_aud": 300, "scope": "phone"},
        "Phone trade-ins accepted, capped at $300. Laptops and tablets are not "
        "accepted.",
        ceiling="300.00", conditions=("trade_in_device",),
    ),
    record(
        "ng-delivery-free-75", NORTHGEAR, BenefitType.DELIVERY,
        {"free_over_aud": 75},
        "Free standard delivery on orders over $75 -- the lowest threshold of any "
        "major Australian electronics retailer.",
        ceiling="8.95", conditions=("order_over_75",),
    ),
]

#: Published with no signature and no key id, and never signed. There is no
#: source span because there is no sentence to quote: the section is adjectives,
#: with no emissions statement, no assurance and no number behind them. It has
#: to reach the screen in order to lose there.
NORTHGEAR_UNSIGNED = record(
    "ng-sustainability-claim", NORTHGEAR, BenefitType.SUSTAINABILITY,
    {"claim": "Australia's most sustainable electronics retailer, "
              "100% carbon neutral, ethically sourced"},
    source_span=None,
)


def signer_for(merchant_id: str, issuer: str) -> ES256Signer:
    """Load this merchant's signing key, minting one the first time only."""
    KEYS.mkdir(parents=True, exist_ok=True)
    pem = KEYS / f"{merchant_id}.pem"
    key_id = f"{merchant_id}-2026-09"
    if pem.exists():
        private = serialization.load_pem_private_key(pem.read_bytes(), password=None)
    else:
        private = ec.generate_private_key(ec.SECP256R1())
        pem.write_bytes(private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        print(f"  minted {pem.relative_to(ROOT)} (gitignored -- do not commit)")
    return ES256Signer(private, key_id=key_id, issuer=issuer)


def publish(merchant_id: str, issuer: str, records: list[BenefitRecord],
            unsigned: list[BenefitRecord] = ()) -> None:
    signer = signer_for(merchant_id, issuer)

    jwk = KEYS / f"{merchant_id}.pub.json"
    jwk.write_text(
        json.dumps([signer.public_key_jwk()], indent=2) + "\n", encoding="utf-8",
    )

    signed = [signer.sign(item) for item in records]
    for item in signed:
        assert signer.verify(item), f"{item.record.record_id} did not verify after signing"
    published = signed + [
        SignedRecord(record=item, signature="", key_id="") for item in unsigned
    ]

    out = RECORDS / f"{merchant_id}.signed.json"
    dump_signed(out, merchant_id, published)
    priced = sum(1 for item in signed if item.record.is_priced)
    print(
        f"  {out.relative_to(ROOT)}: {len(signed)} signed "
        f"({priced} priced, {len(signed) - priced} values), {len(published) - len(signed)} unsigned"
    )


def main() -> None:
    print("Voltway")
    publish("voltway", VOLTWAY, VOLTWAY_RECORDS)
    print("NorthGear")
    publish("northgear", NORTHGEAR, NORTHGEAR_RECORDS, [NORTHGEAR_UNSIGNED])
    print("CityCircuit")
    print("  publishes nothing, by design -- it has the policies, an agent "
          "just cannot read them")


if __name__ == "__main__":
    main()
