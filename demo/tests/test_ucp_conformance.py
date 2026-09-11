"""Conformance checks against the LIVE UCP head — run, not asserted.

Each test drives the real HTTP surface the way an agent would. The last
test deliberately breaks a declaration to prove the checks can fail —
a conformance suite that cannot fail proves nothing.
"""

import threading
import uuid

import httpx
import pytest

from agentbridge import loyalty
from agentbridge.adapters.mock import MockStoreAdapter
from agentbridge.models import OfferCard
from agentbridge.ucp import (
    BENEFIT_VALUE,
    CATALOG_LOOKUP,
    CATALOG_SEARCH,
    CHECKOUT,
    IDENTITY_LINKING,
    negotiate,
    serve_in_thread,
)

PORT = 8033
PLAIN = f"t/0.1; capabilities={CATALOG_SEARCH},{CATALOG_LOOKUP}"
FULL = ("t/0.1; capabilities="
        f"{CATALOG_SEARCH},{CATALOG_LOOKUP},{IDENTITY_LINKING},"
        f"{CHECKOUT},{BENEFIT_VALUE}")


@pytest.fixture(scope="module")
def client():
    server = serve_in_thread(MockStoreAdapter(), PORT)
    c = httpx.Client(base_url=f"http://127.0.0.1:{PORT}", timeout=10)
    yield c
    c.close()
    server.shutdown()


def test_well_known_serves_declaration_and_key(client):
    decl = client.get("/.well-known/ucp").json()["declaration"]
    assert BENEFIT_VALUE in decl["capabilities"]
    ext = decl["capabilities"][BENEFIT_VALUE][0]
    assert ext["extends"] == CATALOG_LOOKUP
    assert len(ext["signing_public_key"]) == 64  # 32-byte ed25519 key, hex


def test_plain_agent_gets_no_extension_and_nothing_breaks(client):
    r = client.get("/ucp/catalog/lookup", params={"id": "prod_charger_gan"},
                   headers={"UCP-Agent": PLAIN}).json()
    assert "extensions" not in r["result"]
    assert r["result"]["offer"]["total_cents"] == 4200
    assert BENEFIT_VALUE not in r["ucp"]["negotiated"]


def test_missing_header_defaults_to_legacy_catalog_caps(client):
    r = client.get("/ucp/catalog/search", params={"q": "hoodie"}).json()
    assert sorted(r["ucp"]["negotiated"]) == sorted([CATALOG_SEARCH, CATALOG_LOOKUP])
    assert r["result"]["count"] > 0


def test_orphan_extension_is_pruned(client):
    orphan = f"t/0.1; capabilities={CATALOG_SEARCH},{BENEFIT_VALUE}"
    r = client.get("/ucp/catalog/search", params={"q": "x"},
                   headers={"UCP-Agent": orphan}).json()
    assert r["ucp"]["negotiated"] == [CATALOG_SEARCH]


def test_unnegotiated_capability_is_refused(client):
    r = client.post("/ucp/checkout", json={"items": [], "idempotency_key": "x"},
                    headers={"UCP-Agent": PLAIN})
    assert r.status_code == 400
    assert CHECKOUT in r.json()["error"]


def test_extended_agent_gets_signed_cards_that_verify(client):
    decl = client.get("/.well-known/ucp").json()["declaration"]
    key = decl["capabilities"][BENEFIT_VALUE][0]["signing_public_key"]
    r = client.get("/ucp/catalog/lookup", params={"id": "prod_charger_gan"},
                   headers={"UCP-Agent": FULL}).json()
    block = r["result"]["extensions"][BENEFIT_VALUE]
    signed = [c for c in block["cards"] if c["signature"]]
    assert signed, "no signed cards on the wire"
    for c in signed:  # verify from wire data alone
        assert loyalty.verify_card(OfferCard(**c), key)


def test_unsigned_card_travels_but_never_verifies(client):
    r = client.get("/ucp/catalog/lookup", params={"id": "prod_charger_gan"},
                   headers={"UCP-Agent": FULL}).json()
    block = r["result"]["extensions"][BENEFIT_VALUE]
    flash = next(c for c in block["cards"]
                 if c["card_id"] == "obc_flash_agent_bonus")
    assert flash["signature"] is None
    verdict = next(v for v in block["valuation"]["verdicts"]
                   if v["card_id"] == "obc_flash_agent_bonus")
    assert not verdict["verified"] and not verdict["credited"]
    assert block["valuation"]["unsigned_penalty_cents"] > 0


def test_identity_link_then_member_priced_checkout(client):
    token = client.post("/ucp/identity/link", json={"email": "ava@example.com"},
                        headers={"UCP-Agent": FULL}).json()["result"]["link_token"]
    headers = {"UCP-Agent": FULL, "UCP-Link": token}
    key = f"conf-{uuid.uuid4().hex[:8]}"
    order = client.post("/ucp/checkout",
                        json={"items": [{"product_id": "prod_charger_gan",
                                         "quantity": 1}],
                              "idempotency_key": key},
                        headers=headers).json()["result"]
    assert order["total_cents"] == 3780 and order["loyalty_credit_cents"] == 420
    replay = client.post("/ucp/checkout",
                         json={"items": [{"product_id": "prod_charger_gan",
                                          "quantity": 1}],
                               "idempotency_key": key},
                         headers=headers).json()["result"]
    assert replay["order_id"] == order["order_id"]
    assert replay["total_cents"] == 3780  # no double discount on replay
    conf = client.post("/ucp/checkout/confirm",
                       json={"order_id": order["order_id"]},
                       headers=headers).json()["result"]
    assert conf["status"] == "CONFIRMED" and conf["total_cents"] == 3780


def test_the_checks_can_fail():
    """Break the extension's parent namespace and negotiation must NOT
    keep the extension alive — proving the pruning logic is load-bearing,
    not decorative."""
    broken = {
        CATALOG_SEARCH: [{"version": "2026-04-08"}],
        BENEFIT_VALUE: [{"version": "2026-08-30",
                         "extends": "dev.ucp.shopping.catalog.lookupTYPO"}],
    }
    active = negotiate([CATALOG_SEARCH, CATALOG_LOOKUP, BENEFIT_VALUE],
                       capabilities=broken)
    assert BENEFIT_VALUE not in active
