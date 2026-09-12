"""Three independent local merchant services for the discovery demo.

Each merchant exposes the same small UCP-draft-style HTTP contract. Differences
come from merchant data and negotiated capabilities, not agent-side branches.
This keeps the experiment honest: the comparison runner talks to wire data.
"""

from __future__ import annotations

import copy
import json
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from agentbridge import loyalty
from agentbridge.models import MemberTier, OfferCard, cents_to_str
from agentbridge.ucp import (
    BENEFIT_VALUE,
    CATALOG_LOOKUP,
    CATALOG_SEARCH,
    IDENTITY_LINKING,
    negotiate,
    parse_ucp_agent,
)


@dataclass(frozen=True)
class Merchant:
    merchant_id: str
    name: str
    title: str
    description: str
    price_cents: int
    capabilities: dict
    cards: tuple[OfferCard, ...] = ()
    published_key: str | None = None


BASE_CAPABILITIES = {
    CATALOG_SEARCH: [{"version": "2026-04-08"}],
    CATALOG_LOOKUP: [{"version": "2026-04-08"}],
}


def _harbor_cards() -> tuple[OfferCard, ...]:
    """Harbor's approved records, signed under its merchant identity."""
    cards: list[OfferCard] = []
    for original in loyalty.CARDS:
        if original.card_id in {"obc_member_price_10", "obc_gold_warranty_12mo",
                                "obc_gold_express_ship"}:
            card = original.model_copy(deep=True)
            card.issuer = "harbor-tech"
            card.source_quote = card.description
            loyalty.sign_card(card)
            cards.append(card)
    return tuple(cards)


def _sparkline_cards() -> tuple[OfferCard, ...]:
    return (
        OfferCard(
            card_id="spk_warranty_24mo",
            issuer="sparkline",
            benefit_type="warranty",
            description="24-month warranty included on every charger!",
            conditions="Trust us.",
            facts={"extra_warranty_months": 24},
            value_ceiling_cents=800,
            affects_price=False,
            issued_at="2026-08-01",
            expires_at="2027-12-31",
        ),
        OfferCard(
            card_id="spk_bonus_50",
            issuer="sparkline",
            benefit_type="bonus_credit",
            description="$50.00 bonus credit applied at checkout for smart shoppers!!",
            conditions="Today only!!",
            facts={"credit_cents": 5000},
            value_ceiling_cents=5000,
            affects_price=True,
            issued_at="2026-09-01",
            expires_at="2026-12-31",
        ),
        OfferCard(
            card_id="spk_free_express",
            issuer="sparkline",
            benefit_type="shipping",
            description="Free express shipping, always.",
            conditions="",
            facts={"express_fee_waived_cents": 995},
            value_ceiling_cents=995,
            affects_price=False,
            issued_at="2026-08-01",
            expires_at="2027-12-31",
        ),
    )


def merchant_catalog() -> tuple[Merchant, ...]:
    """Return immutable merchant fixtures with one comparable product."""
    harbor_caps = copy.deepcopy(BASE_CAPABILITIES)
    harbor_caps[IDENTITY_LINKING] = [{"version": "2026-04-08"}]
    harbor_caps[BENEFIT_VALUE] = [{
        "version": "2026-08-30",
        "extends": CATALOG_LOOKUP,
        "signing_algorithm": "ed25519",
        "signing_public_key": loyalty.PUBLIC_KEY_HEX,
    }]

    spark_caps = copy.deepcopy(BASE_CAPABILITIES)
    spark_caps[BENEFIT_VALUE] = [{
        "version": "2026-08-30",
        "extends": CATALOG_LOOKUP,
        # Deliberately absent signing key: adversarial claims are visible but
        # cannot be credited by an agent.
    }]

    return (
        Merchant(
            merchant_id="harbor-tech",
            name="Harbor Tech",
            title="Harbor 65W GaN Wall Charger",
            description="Dual USB-C + USB-A GaN fast charger, foldable prongs.",
            price_cents=4200,
            capabilities=harbor_caps,
            cards=_harbor_cards(),
            published_key=loyalty.PUBLIC_KEY_HEX,
        ),
        Merchant(
            merchant_id="volt-depot",
            name="Volt Depot",
            title="Volt 65W GaN Fast Charger",
            description="65W USB-C GaN charger, compact housing.",
            price_cents=3850,
            capabilities=copy.deepcopy(BASE_CAPABILITIES),
        ),
        Merchant(
            merchant_id="sparkline",
            name="Sparkline",
            title="Spark 65W GaN Charger Pro",
            description="65W GaN charger with smart power split.",
            price_cents=3995,
            capabilities=spark_caps,
            cards=_sparkline_cards(),
        ),
    )


def _product(merchant: Merchant) -> dict:
    return {
        "id": f"sku_{merchant.merchant_id}_gan65",
        "title": merchant.title,
        "description": merchant.description,
        "category": "electronics",
        "attributes": {"power_watts": 65, "connector": "USB-C", "type": "GaN"},
        "price": {
            "amount_cents": merchant.price_cents,
            "currency": "USD",
            "display": cents_to_str(merchant.price_cents),
        },
        "availability": "in_stock",
        "delivery_sla_days": 2,
        "return_policy": "30-day returns on unused items",
    }


def _declaration(merchant: Merchant) -> dict:
    return {
        "merchant": merchant.merchant_id,
        "merchant_name": merchant.name,
        "ucp": "draft",
        "capabilities": merchant.capabilities,
    }


def _lookup(merchant: Merchant, negotiated: list[str], quantity: int) -> dict:
    product = _product(merchant)
    result = {
        "item": product,
        "offer": {
            "product_id": product["id"],
            "quantity": quantity,
            "unit_price_cents": merchant.price_cents,
            "total_cents": merchant.price_cents * quantity,
            "currency": "USD",
            "available": True,
            "delivery_sla_days": 2,
        },
    }
    if BENEFIT_VALUE in negotiated:
        member = None
        if merchant.merchant_id == "harbor-tech":
            member = {
                "identity_linked": True,
                "member": {"email": "ava@example.com", "tier": MemberTier.GOLD.value,
                           "points": 4200},
            }
        else:
            member = {"identity_linked": False}
        result["extensions"] = {BENEFIT_VALUE: {
            "issuer": merchant.merchant_id,
            "signing_public_key": merchant.published_key,
            "member_context": member,
            "benefit_records": [c.model_dump(mode="json") for c in merchant.cards],
        }}
    return result


def build_merchant_handler(merchant: Merchant):
    class MerchantHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _send(self, body: dict, status: int = 200, negotiated: list[str] | None = None):
            envelope = {
                "ucp": {"version": "draft", "merchant": merchant.merchant_id,
                        "negotiated": negotiated or []},
                **body,
            }
            data = json.dumps(envelope).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _negotiated(self) -> list[str]:
            return negotiate(parse_ucp_agent(self.headers.get("UCP-Agent")),
                             capabilities=merchant.capabilities)

        def do_GET(self):
            url = urlparse(self.path)
            query = parse_qs(url.query)
            negotiated = self._negotiated()
            if url.path == "/.well-known/ucp":
                self._send({"declaration": _declaration(merchant)})
                return
            if url.path == "/ucp/catalog/search":
                if CATALOG_SEARCH not in negotiated:
                    self._send({"error": "catalog search not negotiated"}, 406, negotiated)
                    return
                q = query.get("q", [""])[0].casefold()
                item = _product(merchant)
                searchable = json.dumps(item).casefold()
                stop_words = {"a", "an", "the", "me", "find", "good", "which",
                              "merchant", "should", "i", "buy", "from", "under",
                              "below", "for", "around", "please"}
                tokens = [token for token in q.replace("$", " ").split()
                          if token not in stop_words and not token.isdigit()]
                items = [item] if not tokens or any(token in searchable for token in tokens) else []
                self._send({"result": {"items": items, "count": len(items)}},
                           negotiated=negotiated)
                return
            if url.path == "/ucp/catalog/lookup":
                if CATALOG_LOOKUP not in negotiated:
                    self._send({"error": "catalog lookup not negotiated"}, 406, negotiated)
                    return
                try:
                    quantity = int(query.get("quantity", ["1"])[0])
                except ValueError:
                    self._send({"error": "quantity must be an integer"}, 400, negotiated)
                    return
                if quantity < 1 or quantity > 100:
                    self._send({"error": "quantity must be between 1 and 100"}, 400, negotiated)
                    return
                self._send({"result": _lookup(merchant, negotiated, quantity)},
                           negotiated=negotiated)
                return
            self._send({"error": "unknown path"}, 404, negotiated)

    return MerchantHandler


def serve_merchant(merchant: Merchant, port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), build_merchant_handler(merchant))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def serve_network(base_port: int = 8041) -> tuple[dict[str, str], list[ThreadingHTTPServer]]:
    """Start all merchants and return `{merchant_id: base_url}` plus servers."""
    urls: dict[str, str] = {}
    servers: list[ThreadingHTTPServer] = []
    for offset, merchant in enumerate(merchant_catalog()):
        port = base_port + offset
        servers.append(serve_merchant(merchant, port))
        urls[merchant.merchant_id] = f"http://127.0.0.1:{port}"
    return urls, servers


def stop_network(servers: list[ThreadingHTTPServer]) -> None:
    for server in servers:
        server.shutdown()
        server.server_close()
