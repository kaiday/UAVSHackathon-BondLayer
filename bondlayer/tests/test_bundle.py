"""What the bundler must and must not do.

The "must not" half carries as much weight as the "must" half. A bundler that
quietly re-matches, crosses a merchant boundary, or leaks onto the wire for an
agent that never negotiated the extension would break claims the rest of the
project is built on, and none of those failures is visible in a screenshot.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bondlayer.adapters.catalog import CsvCatalogAdapter
from bondlayer.bundle import CategoryBundler, compose, role_of
from bondlayer.interpreter.parser import parse
from bondlayer.interpreter.resolver import resolve_detailed
from bondlayer.types import Bundle, Constraint, ConstraintKind, Proposal
from bondlayer.ucp.capabilities import BENEFIT_VALUE, CATALOG_LOOKUP, CATALOG_SEARCH
from bondlayer.ucp.server import create_app

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog" / "electronics.csv"
REQUESTS = ROOT / "data" / "eval" / "requests.json"

AWARE = f"{CATALOG_SEARCH};{CATALOG_LOOKUP};{BENEFIT_VALUE}"
PLAIN = f"{CATALOG_SEARCH};{CATALOG_LOOKUP}"


@pytest.fixture(scope="module")
def skus():
    return CsvCatalogAdapter(CATALOG).load()


@pytest.fixture(scope="module")
def requests_by_id() -> dict[str, dict]:
    payload = json.loads(REQUESTS.read_text(encoding="utf-8"))
    return {r["id"]: r for r in payload["requests"]}


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


def bundles_for(utterance: str, skus) -> list[Bundle]:
    """The real path: parse, resolve, then compose over what the resolver gave."""
    constraints = parse(utterance)
    proposals = resolve_detailed(constraints, skus, []).proposals
    return compose(constraints, proposals)


# --- the worked example ------------------------------------------------------


def test_podcasting_request_yields_a_multi_item_same_merchant_bundle(skus, requests_by_id):
    """The problem statement's own worked example, near-verbatim (R07)."""
    bundles = bundles_for(requests_by_id["R07"]["utterance"], skus)
    assert bundles, "a podcasting request must compose a set"
    best = bundles[0]

    assert len(best.items) > 1, "a kit is not one microphone"
    merchants = {p.sku.attributes["merchant"] for p in best.items}
    assert len(merchants) == 1, f"a bundle never crosses merchants: {merchants}"

    # A kit, not three of the same thing: every item fills a different role.
    roles = [role_of(p) for p in best.items]
    assert None not in roles, "every item in a kit must have a readable role"
    assert len(set(roles)) == len(roles), f"duplicate roles in the set: {roles}"
    assert "microphone" in roles and "headphones" in roles

    assert best.rationale.strip(), "a set with no reason to be a set is a list"
    assert best.combined_shelf_price == sum(
        (p.sku.shelf_price for p in best.items), Decimal("0"),
    )


def test_rationale_is_about_togetherness_not_per_item_fit(skus, requests_by_id):
    """Each item's fit is already written on its own ResolvedConstraints.

    The rationale answers the only question a set raises that its members do
    not, so it must not simply describe a part that is not even in the set.
    """
    best = bundles_for(requests_by_id["R07"]["utterance"], skus)[0]
    roles = {role_of(p) for p in best.items}
    if "cable" not in roles:
        assert "cable" not in best.rationale.lower()
    if "stand" not in roles:
        assert "boom arm" not in best.rationale.lower()
    assert "together" in best.rationale.lower()


def test_combined_price_is_the_ceiling_on_a_bundle_request(skus, requests_by_id):
    """R06 says "under $1,200 all up" -- the set is what has to fit."""
    request = requests_by_id["R06"]
    bundles = bundles_for(request["utterance"], skus)
    assert bundles
    for bundle in bundles:
        assert bundle.combined_shelf_price <= Decimal("1200"), bundle.bundle_id
        assert not bundle.unsatisfied, "the ceiling was met, so nothing is unsatisfied"
    # ...and the set-level resolution says so, against the combined price.
    resolved = bundles[0].resolved
    assert any(r.evidence_attribute == "combined_shelf_price" and r.satisfied
               for r in resolved)


# --- the degenerate case -----------------------------------------------------


def test_a_single_viable_sku_yields_a_one_item_bundle(skus):
    """A bundle of one is an answer, not a failure.

    "The ThinkBook 14 G3 with 16 gigs" names one machine. Nothing on the shelf
    complements it here, so the honest set is that machine on its own -- and
    exactly one bundle comes back, not one per merchant, because a set of one
    per merchant is the ranking again with a box drawn round it.
    """
    bundles = bundles_for("The ThinkBook 14 G3 with 16 gigs", skus)
    assert len(bundles) == 1
    best = bundles[0]
    assert len(best.items) == 1
    assert best.combined_shelf_price == best.items[0].sku.shelf_price
    assert "bundle of one" in best.rationale.lower()
    assert best.rationale.strip()


def test_naming_one_part_gets_one_part_not_a_kit(skus, requests_by_id):
    """"A headset for calls under $300" asks for a headset, not a studio."""
    best = bundles_for(requests_by_id["R14"]["utterance"], skus)[0]
    assert len(best.items) == 1
    assert role_of(best.items[0]) == "headphones", best.items[0].sku.title


def test_no_proposals_means_no_bundles():
    assert compose([], []) == []


# --- what it must never do ---------------------------------------------------


def test_every_item_came_from_the_proposals_it_was_handed(skus, requests_by_id):
    """The bundler composes; it never matches, so it can never add a listing."""
    constraints = parse(requests_by_id["R06"]["utterance"])
    proposals = resolve_detailed(constraints, skus, []).proposals
    allowed = {id(p) for p in proposals}
    for bundle in compose(constraints, proposals):
        for item in bundle.items:
            assert id(item) in allowed, f"{item.sku.sku_id} was not a proposal"


def test_no_bundle_ever_crosses_a_merchant(skus, requests_by_id):
    for request in requests_by_id.values():
        for bundle in bundles_for(request["utterance"], skus):
            merchants = {p.sku.attributes["merchant"] for p in bundle.items}
            assert len(merchants) == 1, f"{request['id']}: {merchants}"


def test_composing_is_deterministic(skus, requests_by_id):
    """No clock, no random seed: two runs give identical ids and prices."""
    utterance = requests_by_id["R06"]["utterance"]
    first = bundles_for(utterance, skus)
    second = bundles_for(utterance, skus)
    assert [b.bundle_id for b in first] == [b.bundle_id for b in second]
    assert [b.combined_shelf_price for b in first] == [b.combined_shelf_price for b in second]
    assert [[p.sku.sku_id for p in b.items] for b in first] == \
           [[p.sku.sku_id for p in b.items] for b in second]


def test_category_bundler_satisfies_the_protocol(skus, requests_by_id):
    """`types.Bundler` is not `@runtime_checkable` and `types.py` is read-only
    on a feature branch, so the protocol is checked structurally: the method
    exists, takes the two named arguments, and returns `Bundle`s."""
    import inspect

    bundler = CategoryBundler()
    signature = inspect.signature(bundler.compose)
    assert list(signature.parameters) == ["constraints", "proposals"]

    constraints = parse(requests_by_id["R07"]["utterance"])
    proposals = resolve_detailed(constraints, skus, []).proposals
    out = bundler.compose(constraints, proposals)
    assert isinstance(out, list) and out
    assert all(isinstance(b, Bundle) for b in out)
    assert all(isinstance(p, Proposal) for b in out for p in b.items)


def test_items_keep_the_notes_they_arrived_with(skus):
    """A bundle never rewrites an item's justification -- it carries it."""
    utterance = "Everything I need to start a podcast, under $1,200 all up"
    constraints = parse(utterance)
    proposals = resolve_detailed(constraints, skus, []).proposals
    by_sku = {p.sku.sku_id: p for p in proposals}
    for bundle in compose(constraints, proposals):
        for item in bundle.items:
            assert item.resolved == by_sku[item.sku.sku_id].resolved


# --- the gold sets -----------------------------------------------------------


@pytest.mark.parametrize("request_id", ["R06", "R07"])
def test_bundle_items_are_all_in_the_frozen_gold_set(request_id, skus, requests_by_id):
    request = requests_by_id[request_id]
    gold = set(request["gold_skus"])
    best = bundles_for(request["utterance"], skus)[0]
    got = {p.sku.sku_id for p in best.items}
    assert got <= gold, f"{request_id}: outside gold -- {sorted(got - gold)}"


def test_r24_hits_gold_on_the_laptop_and_misses_on_the_dock(skus, requests_by_id):
    """Reported, not fixed. R24's own note says "BUNDLE across two categories"
    and its utterance asks for "a work laptop and a dock", but the frozen
    `gold_skus` list laptop SKUs only -- there is not one accessory in it. So
    the composed set is right and the gold set cannot score it: the laptop is
    in gold and the dock never could be.

    `data/eval/requests.json` is frozen (rule 4: if the eval says the product is
    wrong, the product is wrong), so this test pins the disagreement in place
    rather than resolving it. If the gold set is ever widened to include docks,
    this test is the one that should fail.
    """
    request = requests_by_id["R24"]
    gold = set(request["gold_skus"])
    best = bundles_for(request["utterance"], skus)[0]

    assert len(best.items) == 2
    anchor, complement = best.items
    assert anchor.sku.category == "laptop"
    assert anchor.sku.sku_id in gold, "the anchor must be a gold laptop"
    assert complement.sku.category == "accessory"
    assert role_of(complement) in ("dock", "hub")
    assert complement.sku.sku_id not in gold
    assert not any(s.startswith(("VOL-008", "VOL-009", "VOL-010")) for s in gold), (
        "R24's gold set contains no accessory; if that changes, revisit this test"
    )


# --- the wire ----------------------------------------------------------------


def _bundles_block(body: dict) -> dict | None:
    blocks = body.get("extensions", {}).get(BENEFIT_VALUE) or []
    return next((b for b in blocks if b.get("kind") == "bundles"), None)


def test_negotiated_agent_sees_bundles_on_the_wire(client):
    body = client.get(
        "/voltway/ucp/catalog/search?category=audio&max_price=1200&limit=40",
        headers={"UCP-Agent": AWARE},
    ).json()
    block = _bundles_block(body)
    assert block is not None, "a negotiated agent must see bundles[]"
    assert block["bundles"], "voltway stocks a whole podcasting shelf"
    bundle = block["bundles"][0]
    assert bundle["rationale"].strip()
    assert Decimal(bundle["combined_shelf_price"]) == sum(
        (Decimal(i["shelf_price"]) for i in bundle["items"]), Decimal("0"),
    )
    assert {i["sku_id"] for i in bundle["items"]} <= {
        p["id"] for p in body["products"]
    }, "a served bundle may only contain listings this response served"


def test_an_agent_that_did_not_negotiate_sees_nothing_new(client):
    """The whole before/after comparison rests on this."""
    body = client.get(
        "/voltway/ucp/catalog/search?category=audio&max_price=1200&limit=40",
        headers={"UCP-Agent": PLAIN},
    ).json()
    assert "extensions" not in body
    assert "bundles" not in json.dumps(body)


def test_the_control_merchant_serves_no_bundles_even_to_a_negotiated_agent(client):
    """citycircuit publishes no extension, so it cannot carry the block --
    and it is the same server and the same builder, not a strawman."""
    body = client.get(
        "/citycircuit/ucp/catalog/search?category=audio&limit=40",
        headers={"UCP-Agent": AWARE},
    ).json()
    assert BENEFIT_VALUE not in body.get("extensions", {})
    assert "bundles" not in json.dumps(body)
    assert body["products"], "the control must still serve a real catalogue"


def test_bundles_do_not_disturb_the_per_sku_blocks(client):
    """The block is appended, carries `sku_id: None`, and is skipped by every
    consumer that maps the list by sku_id or reads it positionally."""
    body = client.get(
        "/voltway/ucp/catalog/search?category=audio&limit=5",
        headers={"UCP-Agent": AWARE},
    ).json()
    blocks = body["extensions"][BENEFIT_VALUE]
    per_sku = [b for b in blocks if b.get("kind") != "bundles"]
    assert [b["sku_id"] for b in per_sku] == [p["id"] for p in body["products"]]
    assert blocks[0]["sku_id"] == body["products"][0]["id"]
    assert all(b["sku_id"] is None for b in blocks if b.get("kind") == "bundles")


def test_lookup_carries_no_bundles(client):
    """A lookup is one listing; a set of one adds nothing to it."""
    sku = client.get(
        "/voltway/ucp/catalog/search?category=audio&limit=1",
        headers={"UCP-Agent": AWARE},
    ).json()["products"][0]["id"]
    body = client.get(
        f"/voltway/ucp/catalog/lookup?sku_id={sku}", headers={"UCP-Agent": AWARE},
    ).json()
    assert _bundles_block(body) is None


def test_a_named_product_gets_one_item_not_a_pitched_kit(client):
    """The same rule on the merchant's side of the wire: `q` names one thing."""
    body = client.get(
        "/voltway/ucp/catalog/search?q=SM7B", headers={"UCP-Agent": AWARE},
    ).json()
    block = _bundles_block(body)
    assert block is not None
    assert all(len(b["items"]) == 1 for b in block["bundles"])


# --- the composition root ----------------------------------------------------


def _fetch_from(client):
    def fetch(merchant: str, query: str, *, extension: bool, plan: dict | None = None) -> dict:
        params = {"limit": 100}
        if plan:
            if plan.get("category"):
                params["category"] = str(plan["category"])
            if plan.get("max_price") is not None:
                params["max_price"] = float(plan["max_price"])
            if plan.get("terms"):
                params["q"] = " ".join(str(t) for t in plan["terms"])
        header = PLAIN + (f";{BENEFIT_VALUE}" if extension else "")
        response = client.get(f"/{merchant}/ucp/catalog/search", params=params,
                              headers={"UCP-Agent": header})
        response.raise_for_status()
        return response.json()
    return fetch


MERCHANTS = ["voltway", "citycircuit", "northgear"]


def test_run_request_without_a_bundler_is_unchanged(client):
    from bondlayer.agent import Phase, run_request

    run = run_request("Beginner-friendly podcasting gear", MERCHANTS,
                      _fetch_from(client), parse=parse)
    assert run.bundles == []
    assert not [s for s in run.steps if s.phase is Phase.BUNDLE]


def test_run_request_with_a_bundler_records_a_bundle_phase(client):
    from bondlayer.agent import Outcome, Phase, run_request

    run = run_request("Beginner-friendly podcasting gear", MERCHANTS,
                      _fetch_from(client), parse=parse, bundler=CategoryBundler())
    assert run.bundles
    steps = [s for s in run.steps if s.phase is Phase.BUNDLE]
    assert len(steps) == 1 and steps[0].outcome is Outcome.OK
    assert steps[0].detail["items"] == [p.sku.sku_id for p in run.bundles[0].items]
    # Composition happens after ranking and can never reorder it.
    assert run.steps.index(steps[0]) > max(
        i for i, s in enumerate(run.steps) if s.phase is Phase.RANKING
    )


def test_bundling_never_changes_the_ranking(client):
    """The headline number must not move because a bundler was wired in."""
    from bondlayer.agent import run_request

    utterance = ("A laptop under $1,500 I can return easily if it turns out not "
                 "to suit my work, from a brand that actually repairs things")
    kwargs = dict(parse=parse)
    plain = run_request(utterance, MERCHANTS, _fetch_from(client), **kwargs)
    bundled = run_request(utterance, MERCHANTS, _fetch_from(client),
                          bundler=CategoryBundler(), **kwargs)
    assert plain.ranked == bundled.ranked


def test_a_bundler_that_returns_nothing_degrades_honestly(client):
    from bondlayer.agent import Outcome, Phase, run_request

    class Empty:
        def compose(self, constraints, proposals):
            return []

    run = run_request("Beginner-friendly podcasting gear", MERCHANTS,
                      _fetch_from(client), parse=parse, bundler=Empty())
    assert run.bundles == []
    step, = [s for s in run.steps if s.phase is Phase.BUNDLE]
    assert step.outcome is Outcome.DEGRADED


def test_proposals_handed_to_the_bundler_are_in_ranked_order(client):
    """The bundler picks the first acceptable item in the order it is given, so
    that order has to be the agent's own ranking or the pick is meaningless."""
    from bondlayer.agent import run_request

    seen: list[list[Proposal]] = []

    class Spy:
        def compose(self, constraints, proposals):
            seen.append(list(proposals))
            return compose(constraints, proposals)

    run = run_request("A laptop under $1,500", MERCHANTS, _fetch_from(client),
                      parse=parse, bundler=Spy())
    assert seen and [p.sku.sku_id for p in seen[0]] == [r.sku_id for r in run.ranked]


def test_constraints_reach_the_bundler_with_their_kinds_intact(client):
    from bondlayer.agent import run_request

    seen: list[list[Constraint]] = []

    class Spy:
        def compose(self, constraints, proposals):
            seen.append(list(constraints))
            return []

    run_request("A laptop under $1,500 I can return easily", MERCHANTS,
                _fetch_from(client), parse=parse, bundler=Spy())
    assert seen and all(isinstance(c, Constraint) for c in seen[0])
    assert any(c.kind is ConstraintKind.HARD for c in seen[0])
