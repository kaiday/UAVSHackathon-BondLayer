"""Builds the three-merchant demo scenario (D9.2).

The cast:

  alpine    runs BondLayer. Dearer at list ($199) and genuinely so -- it must
            deserve to lose the baseline (D5). Wins on adjusted cost.
  peak      plain UCP, cheapest at list ($179), publishes nothing beyond price.
            This is every UCP merchant today.
  ridgeway  plain UCP at $195, and makes an UNSIGNED warranty claim -- the
            adversary that makes signing worth having (D9.3).

All three list the same jacket, with the same GTIN, so the comparison is
genuinely like-for-like.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .ingest.catalog_adapter import IngestIssue, adapt_csv
from .schema import BenefitType, BenefitValue, Conditions, MemberContext
from .signing import MerchantSigner, load_or_create_keypair
from .ucp.server import MerchantService

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
KEYS = DATA / "keys"

MERCHANTS = {
    "alpine": ("Alpine Outfitters", 8101),
    "peak": ("Peak Supply Co", 8102),
    "ridgeway": ("Ridgeway Gear", 8103),
}

GOLD_MEMBER = MemberContext(
    member_id="member-4417",
    program_name="Summit Club",
    tier="Gold",
    points_active=3120,
    points_pending=400,
    units_to_next_tier=280,
    next_tier="Platinum",
)


#: Fixed reference time. The scenario must be byte-identical on every run:
#: signatures have to be stable, and the pinned baseline of D5 is keyed by a
#: hash of the exact prompt, so a drifting `issued_at` would miss the fixture
#: cache and silently re-rank the demo on stage.
REFERENCE_TIME = datetime(2026, 8, 30, 9, 0, 0, tzinfo=timezone.utc)
BENEFIT_EXPIRY = datetime(2027, 12, 31, 0, 0, 0, tzinfo=timezone.utc)


def _now() -> datetime:
    return REFERENCE_TIME


def alpine_benefits(signer: MerchantSigner, price_aud: float) -> list[BenefitValue]:
    """Alpine's approved, signed benefit set.

    In the live demo these come from the LLM policy converter plus the human
    approval gate (D7). This function is the already-approved result, so the
    scenario is reproducible without a model.

    Every declared_bound_aud here is a CEILING (D4). Raising any of them
    cannot raise the computed value -- see tests/test_invariants.py.
    """
    now = _now()
    expiry = BENEFIT_EXPIRY

    # 2 points per dollar, redeemed at 100 points = $1.
    points_aud = round(price_aud * 2 / 100, 2)

    records = [
        BenefitValue(
            id="alpine-member-price",
            type=BenefitType.member_price,
            title="Gold member price — 5% off full-price items",
            facts={"discount_pct": 5.0, "discount_aud": round(price_aud * 0.05, 2)},
            declared_bound_aud=round(price_aud * 0.05, 2),
            conditions=Conditions(requires_membership=True, requires_tier="Gold",
                                  excludes_sale_items=True),
            issuer="alpine", issued_at=now, expires_at=expiry,
        ),
        BenefitValue(
            id="alpine-free-returns",
            type=BenefitType.free_returns,
            title="Free returns within 60 days, return postage paid",
            # The return-label fee Alpine waives is a real, published figure.
            # Recording a live run showed why it has to be here: a model given
            # a benefit with no money attached reads it as a feature bullet and
            # keeps ranking on list price. See DECISIONS.md D9.14.
            facts={"return_window_days": 60, "return_shipping_paid": True,
                   "return_label_fee_waived_aud": 9.95},
            declared_bound_aud=9.95,
            conditions=Conditions(),
            issuer="alpine", issued_at=now, expires_at=expiry,
        ),
        BenefitValue(
            id="alpine-warranty",
            type=BenefitType.warranty_extension,
            title="24 month manufacturer warranty",
            facts={"warranty_months": 24, "statutory_baseline_months": 12},
            conditions=Conditions(),
            issuer="alpine", issued_at=now, expires_at=expiry,
        ),
        BenefitValue(
            id="alpine-free-shipping",
            type=BenefitType.free_shipping,
            title="Free standard delivery over $100 (normally $12.95)",
            facts={"free_over_aud": 100.0, "standard_delivery_fee_aud": 12.95},
            declared_bound_aud=12.95,
            conditions=Conditions(),
            issuer="alpine", issued_at=now, expires_at=expiry,
        ),
        BenefitValue(
            id="alpine-points",
            type=BenefitType.points_earn,
            title="Summit Club points — 2 per dollar, 100 points = $1",
            facts={"points_per_aud": 2, "redemption_points_per_aud": 100,
                   "points_expire_months": 24},
            declared_bound_aud=points_aud,
            conditions=Conditions(requires_membership=True),
            issuer="alpine", issued_at=now, expires_at=expiry,
        ),
        BenefitValue(
            id="alpine-tier-progression",
            type=BenefitType.tier_progression,
            title="280 points from Platinum (free express delivery)",
            facts={"units_to_next_tier": 280, "next_tier": "Platinum"},
            declared_bound_aud=4.00,
            conditions=Conditions(requires_membership=True),
            issuer="alpine", issued_at=now, expires_at=expiry,
        ),
    ]
    return [signer.sign(b) for b in records]


def ridgeway_unsigned_claim(tampered: bool) -> BenefitValue:
    """The adversary (D9.3).

    Ridgeway does not run BondLayer and has no key, so this record carries no
    signature. It is displayed and never valued; the penalty scales with the
    size of the claim (D9.5), so escalating from 2 years to 'lifetime' makes
    Ridgeway rank visibly worse rather than better.
    """
    months = 600 if tampered else 24
    return BenefitValue(
        id="ridgeway-warranty-claim",
        type=BenefitType.warranty_extension,
        title="Lifetime warranty" if tampered else "2 year warranty",
        facts={"warranty_months": months, "statutory_baseline_months": 12},
        issuer="ridgeway",
        issued_at=_now(),
        signature=None,  # the whole point
    )


def build_services(
    *,
    tampered: bool = False,
    inflate_alpine_bounds: float = 1.0,
) -> tuple[dict[str, MerchantService], dict[str, list[IngestIssue]]]:
    """Construct all three merchant services from their native exports.

    inflate_alpine_bounds multiplies every declared bound Alpine publishes.
    It exists so the D4 invariant can be watched failing to do anything.
    """
    services: dict[str, MerchantService] = {}
    all_issues: dict[str, list[IngestIssue]] = {}

    for mid, (name, _port) in MERCHANTS.items():
        offers, issues = adapt_csv(
            DATA / "merchants" / mid / "catalog_export.csv", mid, name
        )
        all_issues[mid] = issues

        if mid == "alpine":
            signer = load_or_create_keypair("alpine", KEYS)
            benefits: dict[str, list[BenefitValue]] = {}
            for offer in offers:
                records = alpine_benefits(signer, offer.price_aud)
                if inflate_alpine_bounds != 1.0:
                    inflated = []
                    for r in records:
                        if r.declared_bound_aud is not None:
                            r = r.model_copy(
                                update={
                                    "declared_bound_aud": round(
                                        r.declared_bound_aud * inflate_alpine_bounds, 2
                                    )
                                }
                            )
                            r = signer.sign(r)  # re-signed: a valid, inflated claim
                        inflated.append(r)
                    records = inflated
                benefits[offer.product_id] = records

            services[mid] = MerchantService(
                mid, name, offers,
                bondlayer_enabled=True,
                public_key_b64=signer.public_key_b64,
                members={GOLD_MEMBER.member_id: GOLD_MEMBER},
                benefits=benefits,
            )
        elif mid == "ridgeway":
            # Plain UCP, but it publishes an unsigned claim anyway. A merchant
            # not running BondLayer cannot sign, which is exactly the point.
            claim = ridgeway_unsigned_claim(tampered)
            services[mid] = MerchantService(
                mid, name, offers,
                bondlayer_enabled=True,      # declares the extension...
                public_key_b64=None,         # ...but publishes no key
                benefits={o.product_id: [claim] for o in offers
                          if "STORM" in o.product_id},
            )
        else:
            services[mid] = MerchantService(mid, name, offers)

    return services, all_issues


def merchant_urls() -> list[str]:
    return [f"http://127.0.0.1:{port}" for _, (_, port) in MERCHANTS.items()]
