"""The flip, on the shipped data: the dearest shelf price wins on effective cost.

These are not unit tests. They run the published records against the frozen
catalogue and the frozen evaluation set, and they fail if the demo stops being
true -- if a ceiling moves, a key rotates without re-signing, or someone signs
the claim that is supposed to stay unsigned.

The premise is checked before the result: Voltway is never the cheapest listing
in these requests. If it ever became the cheapest, winning would prove nothing
and the first test here would say so.
"""

import csv
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from bondlayer.records.serialise import load_signed
from bondlayer.records.signing import ES256Signer
from bondlayer.types import BenefitType, Sku
from bondlayer.valuation import (
    ATTESTED_CONDITIONS,
    MERCHANT_DOMAINS,
    REFERENCE_SHOPPER_POLICY,
    DeterministicValuation,
)

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog" / "electronics.csv"
RECORDS = ROOT / "data" / "records"
KEYS = ROOT / "keys"
EVAL = ROOT / "data" / "eval" / "requests.json"


def _price(raw: str) -> Decimal:
    """`$1,142.96` and `1142.96` are the same money.

    The catalogue carries price defects on purpose -- they are the adapter's
    deliverable, not ours -- so this does the minimum needed to compare.
    """
    return Decimal(re.sub(r"[^0-9.]", "", raw))


@pytest.fixture(scope="module")
def catalog() -> dict[str, Sku]:
    with CATALOG.open(encoding="utf-8", newline="") as handle:
        return {
            row["sku"]: Sku(
                sku_id=row["sku"],
                title=row["title"],
                category=row["category"],
                shelf_price=_price(row["price"]),
                attributes={"merchant": row["merchant"]},
            )
            for row in csv.DictReader(handle)
        }


@pytest.fixture(scope="module")
def published() -> dict[str, list]:
    return {
        merchant: load_signed(RECORDS / f"{merchant}.signed.json")
        for merchant in MERCHANT_DOMAINS
    }


@pytest.fixture(scope="module")
def verifiers() -> dict[str, ES256Signer]:
    """One verifier per merchant, built from the published JWK only.

    No private key, no network: this is exactly what an agent can do from a
    fresh clone, which is the whole claim the signing story makes.
    """
    built = {}
    for merchant, domain in MERCHANT_DOMAINS.items():
        path = KEYS / f"{merchant}.pub.json"
        if path.exists():
            jwk, = json.loads(path.read_text(encoding="utf-8"))
            built[merchant] = ES256Signer.from_jwk(jwk, issuer=domain)
    return built


def _cost(merchant, sku, published, verifiers):
    valuation = DeterministicValuation(
        verifiers[merchant],
        merchant_domains=MERCHANT_DOMAINS,
        satisfied_conditions=ATTESTED_CONDITIONS,
    )
    return valuation.effective_cost(
        sku, published[merchant], REFERENCE_SHOPPER_POLICY,
    )


def _ranked(sku_ids, catalog, published, verifiers):
    """Effective cost for each listing, cheapest first, ties broken by sku id."""
    costs = []
    for sku_id in sku_ids:
        sku = catalog[sku_id]
        merchant = sku.attributes["merchant"]
        if merchant in verifiers:
            costs.append(_cost(merchant, sku, published, verifiers))
        else:  # the control: nothing published, nothing to verify
            costs.append(_cost_free(sku))
    return sorted(costs, key=lambda item: (item.effective_cost, item.sku_id))


def _cost_free(sku):
    from bondlayer.types import EffectiveCost
    return EffectiveCost(sku.sku_id, sku.shelf_price, [], sku.shelf_price)


@pytest.fixture(scope="module")
def requests_by_id() -> dict[str, dict]:
    payload = json.loads(EVAL.read_text(encoding="utf-8"))
    return {item["id"]: item for item in payload["requests"]}


# --- the premise -----------------------------------------------------------


def test_voltway_is_never_the_cheapest_shelf_price(catalog, requests_by_id):
    """If Voltway were cheapest, winning would prove nothing."""
    for request_id in ("R01", "R21"):
        golds = requests_by_id[request_id]["gold_skus"]
        cheapest = min(golds, key=lambda s: (catalog[s].shelf_price, s))
        assert catalog[cheapest].attributes["merchant"] != "voltway", request_id


# --- verification ----------------------------------------------------------


def test_every_published_signature_verifies_from_the_public_key(published, verifiers):
    for merchant, signer in verifiers.items():
        signed = [item for item in published[merchant] if item.signature]
        assert signed, f"{merchant} publishes no signed records"
        assert all(signer.verify(item) for item in signed), merchant


def test_the_planted_claim_is_published_unsigned_and_does_not_verify(published, verifiers):
    unsigned = [item for item in published["northgear"] if not item.signature]
    claim, = unsigned
    assert claim.record.benefit_type is BenefitType.SUSTAINABILITY
    assert claim.record.source_span is None  # nothing a human could approve
    assert not verifiers["northgear"].verify(claim)


def test_the_control_publishes_nothing(published):
    assert published["citycircuit"] == []


# --- the flip --------------------------------------------------------------


def test_r21_voltway_wins_on_effective_cost_despite_the_higher_shelf_price(
    catalog, published, verifiers, requests_by_id,
):
    """The tie-break request. Shelf price says CityCircuit; the records say Voltway."""
    golds = requests_by_id["R21"]["gold_skus"]
    ranked = _ranked(golds, catalog, published, verifiers)
    winner = ranked[0]

    assert catalog[winner.sku_id].attributes["merchant"] == "voltway"
    assert winner.total_credited > 0

    cheapest_shelf = min(
        (catalog[s] for s in golds), key=lambda s: (s.shelf_price, s.sku_id),
    )
    assert winner.shelf_price > cheapest_shelf.shelf_price
    assert winner.effective_cost < cheapest_shelf.shelf_price
    # And the premium the shopper is asked to accept stays inside their policy.
    premium = winner.shelf_price - cheapest_shelf.shelf_price
    assert premium <= REFERENCE_SHOPPER_POLICY.max_premium_over_cheapest_aud


def test_r01_the_demo_query_also_flips(catalog, published, verifiers, requests_by_id):
    golds = requests_by_id["R01"]["gold_skus"]
    winner = _ranked(golds, catalog, published, verifiers)[0]
    assert catalog[winner.sku_id].attributes["merchant"] == "voltway"


def test_the_control_earns_nothing_and_pays_its_shelf_price(catalog, requests_by_id):
    for sku_id in requests_by_id["R21"]["gold_skus"]:
        sku = catalog[sku_id]
        if sku.attributes["merchant"] == "citycircuit":
            cost = _cost_free(sku)
            assert cost.credited == [] and cost.effective_cost == sku.shelf_price


# --- valuation is not verification -----------------------------------------


def test_values_claims_are_citable_and_credit_nothing(catalog, published, verifiers):
    """R12: the signed claim may be cited, the unsigned one may not. Both credit $0."""
    phone = next(
        sku for sku in catalog.values()
        if sku.attributes["merchant"] == "voltway" and sku.category == "phone"
    )
    cost = _cost("voltway", phone, published, verifiers)
    values = [
        line for line in cost.credited
        if line.benefit_type in {
            BenefitType.SUSTAINABILITY, BenefitType.REPAIRABILITY, BenefitType.DURABILITY,
        }
    ]
    assert values, "Voltway publishes no values claims"
    assert all(line.credited_aud == 0 for line in values)
    assert all("citable" in line.reason.lower() for line in values)

    ng_phone = next(
        sku for sku in catalog.values()
        if sku.attributes["merchant"] == "northgear" and sku.category == "phone"
    )
    ng_cost = _cost("northgear", ng_phone, published, verifiers)
    claim, = [
        line for line in ng_cost.credited if line.record_id == "ng-sustainability-claim"
    ]
    assert claim.credited_aud == 0
    assert "unverified" in claim.reason.lower()


def test_a_laptop_does_not_earn_the_appliance_warranty(catalog, published, verifiers):
    """Two warranty records, one benefit type: scope decides which one attaches."""
    laptop = catalog["VOL-0031"]
    cost = _cost("voltway", laptop, published, verifiers)
    attached = [
        line.record_id for line in cost.credited
        if line.benefit_type is BenefitType.WARRANTY and line.credited_aud > 0
    ]
    assert attached == ["vw-warranty-laptop-phone-12"]


def test_the_paid_membership_is_withheld_not_credited(catalog, published, verifiers):
    """NorthGear Plus costs $49/year; an agent cannot credit what is not bought."""
    cost = _cost("northgear", catalog["NOR-0033"], published, verifiers)
    points, = [line for line in cost.credited if line.record_id == "ng-points-2x"]
    assert points.credited_aud == 0
    assert "paid_member" in points.reason
