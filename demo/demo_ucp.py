"""UCP head demo — the whole product in one capability header.

Runs the same catalog.lookup against the same merchant twice. The ONLY
difference is which capabilities the agent declares in its `UCP-Agent`
header — ordinary UCP capability negotiation does the rest:

  plain UCP agent      -> clean catalogue, no benefit data, nothing breaks
  + benefit_value      -> signed Offer Cards + effective-cost valuation

Then it acts as the agent-side valuation library: verifies a card's
Ed25519 signature against the key published in /.well-known/ucp, proves
tampering is detected, and completes a member checkout (PENDING ->
confirm) at the member price.

Fully offline, no keys needed:  python demo_ucp.py
"""

from __future__ import annotations

import json

import httpx

from agentbridge.adapters.mock import MockStoreAdapter
from agentbridge.logging_config import log_event
from agentbridge.models import cents_to_str
from agentbridge.ucp import (
    BENEFIT_VALUE,
    CATALOG_LOOKUP,
    CATALOG_SEARCH,
    CHECKOUT,
    IDENTITY_LINKING,
    serve_in_thread,
)

PORT = 8032
BASE = f"http://127.0.0.1:{PORT}"

PLAIN = f"demo-shopper/0.1; capabilities={CATALOG_SEARCH},{CATALOG_LOOKUP}"
EXTENDED = ("demo-shopper/0.1; capabilities="
            f"{CATALOG_SEARCH},{CATALOG_LOOKUP},{IDENTITY_LINKING},"
            f"{CHECKOUT},{BENEFIT_VALUE}")
ORPHAN = f"demo-shopper/0.1; capabilities={CATALOG_SEARCH},{BENEFIT_VALUE}"

W = 74


def rule(title: str = "") -> None:
    print("=" * W if not title else f"--- {title} ".ljust(W, "-"))


def main() -> None:
    log_event("server_start", transport="ucp_demo")
    server = serve_in_thread(MockStoreAdapter(), PORT)
    client = httpx.Client(base_url=BASE, timeout=10)
    try:
        run(client)
    finally:
        client.close()
        server.shutdown()


def run(client: httpx.Client) -> None:
    rule()
    print(f"{'AgentBridge UCP head — one merchant, one header, two worlds':^{W}}")
    rule()

    # 1 — the declaration the agent fetches during negotiation
    decl = client.get("/.well-known/ucp").json()["declaration"]
    ext = decl["capabilities"][BENEFIT_VALUE][0]
    print(f"\n[1] GET /.well-known/ucp  (merchant: {decl['merchant']})")
    print(f"    declares: {', '.join(sorted(decl['capabilities']))}")
    print(f"    extension {BENEFIT_VALUE} extends {ext['extends']}")
    print(f"    signing key (ed25519): {ext['signing_public_key'][:24]}…")

    # 2 — plain UCP agent: same endpoint, no extension, nothing breaks
    print(f"\n[2] catalog.lookup as a PLAIN UCP agent")
    r = client.get("/ucp/catalog/lookup", params={"id": "prod_charger_gan"},
                   headers={"UCP-Agent": PLAIN}).json()
    offer = r["result"]["offer"]
    print(f"    negotiated: {', '.join(r['ucp']['negotiated'])}")
    print(f"    offer: {r['result']['item']['title']} — "
          f"{cents_to_str(offer['total_cents'])}")
    print(f"    extensions present: {'extensions' in r['result']}"
          "   <- clean plain UCP, the merchant is fully shoppable")

    # 3 — extension pruning: benefit_value without its parent is dropped
    r = client.get("/ucp/catalog/search", params={"q": "charger"},
                   headers={"UCP-Agent": ORPHAN}).json()
    print(f"\n[3] declaring {BENEFIT_VALUE} WITHOUT catalog.lookup")
    print(f"    negotiated: {', '.join(r['ucp']['negotiated'])}")
    print("    <- the extension was pruned: no parent, no extension. The")
    print("       protocol enforces this, not a special code path.")

    # 4 — identity link, then the same lookup with the extension negotiated
    link = client.post("/ucp/identity/link", json={"email": "ava@example.com"},
                       headers={"UCP-Agent": EXTENDED}).json()["result"]
    token = link["link_token"]
    print(f"\n[4] identity_linking: {link['member']['email']} "
          f"({link['member']['tier']}) -> {token[:14]}…")

    r = client.get("/ucp/catalog/lookup", params={"id": "prod_charger_gan"},
                   headers={"UCP-Agent": EXTENDED, "UCP-Link": token}).json()
    block = r["result"]["extensions"][BENEFIT_VALUE]
    valuation = block["valuation"]
    print(f"\n[5] the SAME lookup with {BENEFIT_VALUE} negotiated")
    print(f"    negotiated: {len(r['ucp']['negotiated'])} capabilities "
          f"(incl. the extension)")
    print(f"    {len(block['cards'])} Offer Cards on the wire; valuation:")
    print(f"      {valuation['arithmetic']}")
    for v in valuation["verdicts"]:
        mark = "credited" if v["credited"] else "     -  "
        flag = "" if v["verified"] else "  [UNSIGNED — never valued]"
        print(f"      [{mark}] {v['card_id']:<28} {v['reason']}{flag}")

    # 5 — act as the agent-side library: verify against the PUBLISHED key
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    pub = Ed25519PublicKey.from_public_bytes(
        bytes.fromhex(ext["signing_public_key"]))
    card = next(c for c in block["cards"] if c["card_id"] == "obc_member_price_10")
    payload = {k: v for k, v in card.items() if k != "signature"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    pub.verify(bytes.fromhex(card["signature"]), canonical)
    print("\n[6] agent-side verification, using only what was on the wire:")
    print(f"    {card['card_id']}: signature VALID for the published key")
    tampered = dict(payload, value_ceiling_cents=999999)
    canonical_bad = json.dumps(tampered, sort_keys=True, separators=(",", ":")).encode()
    try:
        pub.verify(bytes.fromhex(card["signature"]), canonical_bad)
        print("    !! tampered card verified — THIS MUST NEVER PRINT")
    except Exception:
        print("    tampered ceiling ($9,999.99): signature INVALID — caught")

    # 6 — checkout: the offer that won is the offer delivered
    order = client.post("/ucp/checkout",
                        json={"items": [{"product_id": "prod_charger_gan",
                                         "quantity": 1}],
                              "idempotency_key": "ucp-demo-1"},
                        headers={"UCP-Agent": EXTENDED, "UCP-Link": token},
                        ).json()["result"]
    replay = client.post("/ucp/checkout",
                         json={"items": [{"product_id": "prod_charger_gan",
                                          "quantity": 1}],
                               "idempotency_key": "ucp-demo-1"},
                         headers={"UCP-Agent": EXTENDED, "UCP-Link": token},
                         ).json()["result"]
    conf = client.post("/ucp/checkout/confirm",
                       json={"order_id": order["order_id"]},
                       headers={"UCP-Agent": EXTENDED, "UCP-Link": token},
                       ).json()["result"]
    print(f"\n[7] checkout under the link:")
    print(f"    create : {order['order_id']}  list {cents_to_str(order['list_total_cents'])} "
          f"-> charge {order['total']}  (PENDING, no money moved)")
    print(f"    replay : same key -> same order ({replay['order_id']}), "
          "no duplicate, no double discount")
    print(f"    confirm: {conf['status']} — settled {conf['total']} "
          f"(ref {conf['payment_ref']})")

    rule()
    print("Try it by hand (server: python -m agentbridge.ucp):")
    print(f"  curl -s {BASE}/.well-known/ucp")
    print(f"  curl -s -H 'UCP-Agent: {PLAIN}' \\")
    print(f"       '{BASE}/ucp/catalog/lookup?id=prod_charger_gan'")
    print("  # add ,org.bondlayer.benefit_value to the header — that one diff")
    print("  # is the whole product.")
    rule()


if __name__ == "__main__":
    main()
