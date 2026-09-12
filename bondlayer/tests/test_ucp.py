"""The UCP head, and the one property the comparison depends on.

Assumption A2 requires the control merchant and the BondLayer merchant to be
served *identically*, so the only variable is the data exposed. These tests are
what stop that quietly becoming false at 16:00 on day two.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from bondlayer.ucp.capabilities import (
    BENEFIT_VALUE,
    CATALOG_LOOKUP,
    CATALOG_SEARCH,
    IDENTITY_LINKING,
    merchant_capabilities,
    negotiate,
    parse_agent_header,
)
from bondlayer.ucp.server import create_app

AWARE = json.dumps(
    {
        "capabilities": {
            CATALOG_SEARCH: ["2026-04-08"],
            CATALOG_LOOKUP: ["2026-04-08"],
            BENEFIT_VALUE: ["draft"],
        }
    }
)
PLAIN = json.dumps(
    {"capabilities": {CATALOG_SEARCH: ["2026-04-08"], CATALOG_LOOKUP: ["2026-04-08"]}}
)


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


# --- profile ---------------------------------------------------------------


def test_profile_declares_the_extension_against_catalog_not_checkout(client):
    body = client.get("/voltway/.well-known/ucp").json()
    ext = body["extensions"][BENEFIT_VALUE][0]
    # UCP's own loyalty extension hangs off checkout, where the data arrives
    # after the merchant has already been chosen. Ours rides the call the agent
    # makes while it is still comparing.
    assert ext["extends"] == [CATALOG_SEARCH, CATALOG_LOOKUP]
    assert "dev.ucp.shopping.checkout" not in ext["extends"]


def test_extension_is_namespaced_outside_the_reserved_prefix(client):
    body = client.get("/voltway/.well-known/ucp").json()
    name = next(iter(body["extensions"]))
    # dev.ucp.* is reserved for capabilities governed by the UCP Tech Council.
    assert name.startswith("org.bondlayer.")
    assert not name.startswith("dev.ucp.")


def test_control_merchant_publishes_no_extension(client):
    body = client.get("/citycircuit/.well-known/ucp").json()
    assert body["extensions"] == {}
    # ...but it is still a conformant UCP merchant with the base capabilities.
    assert CATALOG_SEARCH in body["capabilities"]
    assert IDENTITY_LINKING in body["capabilities"]


def test_signing_keys_published_for_signers_and_absent_for_the_control(client):
    # Was "empty until Bach publishes". Bach has published, so this now asserts
    # the property it was always protecting: the profile reports what is really
    # there, never crashing and never fabricating a key.
    voltway = client.get("/voltway/.well-known/ucp").json()["signing_keys"]
    assert voltway, "voltway signs records, so it must publish a key"
    assert all(k.get("kid") or k.get("key_id") for k in voltway), (
        "every published key needs an id -- detached signatures reference it"
    )
    # The control does not sign, so an empty list stays a real, valid state.
    assert client.get("/citycircuit/.well-known/ucp").json()["signing_keys"] == []


# --- negotiation -----------------------------------------------------------


def test_negotiation_is_an_intersection_not_a_branch():
    caps = merchant_capabilities(publishes_benefit_extension=True)
    aware = negotiate(caps, parse_agent_header(AWARE))
    plain = negotiate(caps, parse_agent_header(PLAIN))
    assert aware.serves_benefit_extension
    assert not plain.serves_benefit_extension
    assert plain.pruned[BENEFIT_VALUE] == "not declared by the agent"


def test_extension_is_pruned_when_no_parent_survives():
    caps = merchant_capabilities(publishes_benefit_extension=True)
    # An agent that wants the extension but declares neither parent capability.
    only_ext = negotiate(caps, {BENEFIT_VALUE: ("draft",)})
    assert BENEFIT_VALUE not in only_ext
    assert only_ext.pruned[BENEFIT_VALUE] == "no surviving parent capability"


def test_version_mismatch_excludes_the_capability():
    caps = merchant_capabilities(publishes_benefit_extension=True)
    stale = negotiate(caps, {CATALOG_SEARCH: ("2025-01-01",)})
    assert CATALOG_SEARCH not in stale
    assert stale.pruned[CATALOG_SEARCH] == "no mutually supported version"


def test_missing_header_degrades_to_plain_ucp():
    # What every UCP agent in the world does today.
    caps = merchant_capabilities(publishes_benefit_extension=True)
    assert not negotiate(caps, parse_agent_header(None)).serves_benefit_extension


def test_unparseable_header_degrades_rather_than_fails():
    caps = merchant_capabilities(publishes_benefit_extension=True)
    n = negotiate(caps, parse_agent_header("{not json"))
    assert CATALOG_SEARCH in n and not n.serves_benefit_extension


# --- the parity property ---------------------------------------------------


def test_both_agents_get_a_valid_response_from_the_same_route(client):
    url = "/voltway/ucp/catalog/search?category=laptop&limit=5"
    aware = client.get(url, headers={"UCP-Agent": AWARE})
    plain = client.get(url, headers={"UCP-Agent": PLAIN})
    assert aware.status_code == plain.status_code == 200
    assert aware.json()["products"] == plain.json()["products"]
    assert "extensions" in aware.json()
    assert "extensions" not in plain.json()


def test_control_and_bondlayer_differ_only_in_exposed_data(client):
    headers = {"UCP-Agent": AWARE}
    bond = client.get("/voltway/ucp/catalog/search?category=laptop", headers=headers)
    ctrl = client.get("/citycircuit/ucp/catalog/search?category=laptop", headers=headers)
    assert bond.status_code == ctrl.status_code == 200
    # Same shape, same keys, same builder -- the control is not a strawman.
    assert set(ctrl.json()) <= set(bond.json())
    assert ctrl.json()["products"], "the control must serve a real catalogue"
    # The only difference: the control never declared the extension.
    assert BENEFIT_VALUE not in ctrl.json().get("extensions", {})
    assert BENEFIT_VALUE in bond.json()["extensions"]


def test_active_capabilities_are_echoed(client):
    body = client.get(
        "/voltway/ucp/catalog/search?limit=1", headers={"UCP-Agent": AWARE}
    ).json()
    assert BENEFIT_VALUE in body["active_capabilities"]


def test_lookup_carries_the_extension_because_it_is_the_comparison_call(client):
    sku = client.get(
        "/voltway/ucp/catalog/search?category=laptop&limit=1",
        headers={"UCP-Agent": AWARE},
    ).json()["products"][0]["id"]
    body = client.get(
        f"/voltway/ucp/catalog/lookup?sku_id={sku}", headers={"UCP-Agent": AWARE}
    ).json()
    assert body["extensions"][BENEFIT_VALUE][0]["sku_id"] == sku


def test_prices_are_numbers_by_the_time_they_reach_the_wire(client):
    body = client.get(
        "/citycircuit/ucp/catalog/search?category=laptop", headers={"UCP-Agent": PLAIN}
    ).json()
    for product in body["products"]:
        float(product["price"]["amount"])  # raises if "$2133.03" survived


def test_hard_price_filter_applies_to_repaired_prices(client):
    body = client.get(
        "/voltway/ucp/catalog/search?category=laptop&max_price=1500",
        headers={"UCP-Agent": PLAIN},
    ).json()
    assert body["products"], "R01's price filter must return something"
    assert all(float(p["price"]["amount"]) <= 1500 for p in body["products"])


# --- the records seam (Bach's branch feeds this) ---------------------------


def test_records_seam_carries_signed_records(client):
    body = client.get(
        "/voltway/ucp/catalog/search?category=laptop&limit=1",
        headers={"UCP-Agent": AWARE},
    ).json()
    block = body["extensions"][BENEFIT_VALUE][0]
    assert block["records"], "voltway publishes records; the seam is live"
    for entry in block["records"]:
        assert set(entry) >= {"record", "signature", "key_id", "signed"}
        # `signed` is derived by the server, never authored by the merchant.
        assert entry["signed"] is bool(entry["signature"] and entry["key_id"])
    # issuer is the domain, not the merchant id: it is what a record's own
    # issuer field carries and what signing_keys[] is published under.
    assert block["issuer"] == "voltway.example"


def test_merchant_wide_records_attach_to_every_listing(tmp_path):
    from bondlayer.ucp.records import for_sku, load_records

    (tmp_path / "voltway.signed.json").write_text(
        json.dumps(
            [
                {
                    "record": {"record_id": "r-1", "sku_id": None,
                               "benefit_type": "free_returns",
                               "issuer": "voltway.example"},
                    "signature": "sig", "key_id": "k1",
                },
                {
                    "record": {"record_id": "r-2", "sku_id": "VOL-0001",
                               "benefit_type": "warranty",
                               "issuer": "voltway.example"},
                    "signature": "sig", "key_id": "k1",
                },
                {
                    "record": {"record_id": "r-3", "sku_id": None,
                               "benefit_type": "sustainability",
                               "issuer": "voltway.example"},
                },
            ]
        ),
        encoding="utf-8",
    )
    records = load_records("voltway", records_dir=tmp_path)
    assert len(records) == 3
    # A record is signed iff it carries BOTH a signature and a key_id.
    assert [r["signed"] for r in records] == [True, True, False]
    # The unsigned claim is served, not filtered: it has to arrive to lose.
    assert {r["record"]["record_id"] for r in for_sku(records, "VOL-0001")} == {
        "r-1", "r-2", "r-3",
    }
    assert {r["record"]["record_id"] for r in for_sku(records, "VOL-0009")} == {
        "r-1", "r-3",
    }


def test_missing_records_file_is_a_normal_state(tmp_path):
    from bondlayer.ucp.records import load_records

    # The control merchant publishes nothing by design.
    assert load_records("citycircuit", records_dir=tmp_path) == []
