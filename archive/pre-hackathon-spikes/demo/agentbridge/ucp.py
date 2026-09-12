"""The UCP head — the same store, served UCP-draft-style over HTTP.

MCP (server.py) is how Claude Desktop shops here; THIS surface is the
protocol story from the proposal: a merchant-side layer that rides UCP's
own extension mechanism. The hero feature is CAPABILITY NEGOTIATION:

  - An agent declares what it supports in its `UCP-Agent` header.
  - The server activates the intersection (name intersection + extension
    pruning, per ucp.dev core-concepts).
  - An agent that declares `org.bondlayer.benefit_value` receives signed
    Offer Cards and the effective-cost valuation attached to catalog
    lookups. An agent that has never heard of the extension gets plain,
    valid catalogue data — nothing breaks, no special code path.

HONESTY LABEL: this is UCP-DRAFT-STYLE, not certified conformance. The
negotiation semantics follow the published core-concepts; the JSON field
shapes approximate the draft spec. Capability names and the extension id
are shared with the team's BondLayer spike so both pre-work artefacts
speak one vocabulary.

Endpoints:
  GET  /.well-known/ucp                    capability declaration + signing key
  GET  /ucp/catalog/search?q=...           products (plain UCP)
  GET  /ucp/catalog/lookup?id=...&quantity=N[&variant=...]
                                           product + offer [+ benefit_value ext]
  POST /ucp/identity/link                  {"email": ...} -> {"link_token": ...}
  POST /ucp/checkout                       {"items": [...], "idempotency_key": ...}
  POST /ucp/checkout/confirm               {"order_id": ...}

Identity: pass the link_token from /ucp/identity/link in a `UCP-Link`
header; offers and checkout then run under that member (stand-in for
UCP identity linking's OAuth 2.0 account link).

Run standalone:  python -m agentbridge.ucp [port]
In-process:      serve_in_thread(adapter, port)   (used by demo_ucp.py)
"""

from __future__ import annotations

import json
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from agentbridge import loyalty
from agentbridge.adapters.mock import MockStoreAdapter
from agentbridge.logging_config import log_event
from agentbridge.models import Member, cents_to_str
from agentbridge.service import AgentBridgeService

DEFAULT_PORT = 8031

# ------------------------------------------------------------- capabilities --
# Names shared with the BondLayer spike (bach-demo) so the two pre-work
# artefacts agree on vocabulary.

CATALOG_SEARCH = "dev.ucp.shopping.catalog.search"
CATALOG_LOOKUP = "dev.ucp.shopping.catalog.lookup"
IDENTITY_LINKING = "dev.ucp.common.identity_linking"
CHECKOUT = "dev.ucp.shopping.checkout"
BENEFIT_VALUE = "org.bondlayer.benefit_value"

#: What a legacy agent with no UCP-Agent header is assumed to speak.
DEFAULT_AGENT_CAPS = [CATALOG_SEARCH, CATALOG_LOOKUP]


def merchant_declaration() -> dict:
    """The merchant's capability declaration, served at /.well-known/ucp.

    The signing public key is published HERE because the agent already
    fetches this document during negotiation (demo-grade trust root — a
    real deployment needs a registry/CA; same caveat as the team spike).
    """
    return {
        "merchant": loyalty.MERCHANT_ID,
        "ucp": "draft",
        "capabilities": {
            CATALOG_SEARCH: [{"version": "2026-04-08"}],
            CATALOG_LOOKUP: [{"version": "2026-04-08"}],
            IDENTITY_LINKING: [{"version": "2026-04-08"}],
            CHECKOUT: [{"version": "2026-04-08"}],
            BENEFIT_VALUE: [{
                "version": "2026-08-30",
                "extends": CATALOG_LOOKUP,
                "spec": "https://bondlayer.example/spec/benefit_value",
                "signing_algorithm": "ed25519",
                "signing_public_key": loyalty.PUBLIC_KEY_HEX,
            }],
        },
    }


def parse_ucp_agent(header: str | None) -> list[str]:
    """Parse `UCP-Agent: name/ver; capabilities=a,b,c` -> declared names."""
    if not header:
        return list(DEFAULT_AGENT_CAPS)
    for part in header.split(";"):
        part = part.strip()
        if part.startswith("capabilities="):
            caps = part[len("capabilities="):]
            return [c.strip() for c in caps.split(",") if c.strip()]
    return list(DEFAULT_AGENT_CAPS)


def negotiate(agent_declares: list[str],
              capabilities: dict | None = None) -> list[str]:
    """Server-selects: name intersection, then extension pruning (an
    extension whose parent capability did not survive is dropped),
    repeated until stable. `capabilities` defaults to this merchant's
    declaration; compare_llm.py passes other merchants' declarations."""
    ours = capabilities if capabilities is not None \
        else merchant_declaration()["capabilities"]
    active = {name: entries for name, entries in ours.items()
              if name in agent_declares}
    changed = True
    while changed:
        changed = False
        for name in list(active):
            for entry in active[name]:
                parent = entry.get("extends")
                if parent is not None and parent not in active:
                    del active[name]
                    changed = True
                    break
    return sorted(active)


# ------------------------------------------------------------------- server --

class _UCPState:
    def __init__(self, adapter: MockStoreAdapter) -> None:
        self.adapter = adapter
        self.links: dict[str, Member] = {}  # link_token -> member
        self.lock = threading.Lock()        # one order mutation at a time


def _product_json(p) -> dict:
    return {
        "id": p.product_id,
        "title": p.title,
        "description": p.description,
        "category": p.category,
        "price": {"amount_cents": p.price_cents, "currency": p.currency,
                  "display": cents_to_str(p.price_cents, p.currency)},
        "availability": "in_stock" if p.in_stock else "out_of_stock",
        "delivery_sla_days": p.delivery_sla_days,
        "variants": [{"id": v.variant_id, "size": v.size, "color": v.color,
                      "stock": v.stock} for v in p.variants],
    }


def _make_handler(state: _UCPState):
    class UCPHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # keep demo output clean
            pass

        # ---------------------------------------------------------- plumbing

        def _negotiated(self) -> list[str]:
            return negotiate(parse_ucp_agent(self.headers.get("UCP-Agent")))

        def _member(self) -> Member | None:
            token = self.headers.get("UCP-Link", "").strip()
            return state.links.get(token)

        def _service(self) -> AgentBridgeService:
            """A fresh service per request over the shared adapter: the
            member context is per-request in HTTP, unlike the MCP session."""
            svc = AgentBridgeService(state.adapter)
            svc.member = self._member()
            return svc

        def _send(self, body: dict, status: int = 200,
                  negotiated: list[str] | None = None) -> None:
            envelope = {"ucp": {"version": "draft",
                                "merchant": loyalty.MERCHANT_ID,
                                "negotiated": negotiated
                                if negotiated is not None else []},
                        **body}
            data = json.dumps(envelope, default=str).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _json_body(self) -> dict:
            length = int(self.headers.get("Content-Length", 0) or 0)
            try:
                return json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return {}

        # ------------------------------------------------------------ routes

        def do_GET(self):
            url = urlparse(self.path)
            query = parse_qs(url.query)
            negotiated = self._negotiated()
            log_event("ucp_request", method="GET", path=url.path,
                      negotiated=negotiated,
                      member=(self._member().email if self._member() else None))

            if url.path == "/.well-known/ucp":
                self._send({"declaration": merchant_declaration()})
            elif url.path == "/ucp/catalog/search":
                self._catalog_search(query, negotiated)
            elif url.path == "/ucp/catalog/lookup":
                self._catalog_lookup(query, negotiated)
            else:
                self._send({"error": "unknown path"}, status=404)

        def do_POST(self):
            url = urlparse(self.path)
            negotiated = self._negotiated()
            body = self._json_body()
            log_event("ucp_request", method="POST", path=url.path,
                      negotiated=negotiated)

            if url.path == "/ucp/identity/link":
                self._identity_link(body, negotiated)
            elif url.path == "/ucp/checkout":
                self._checkout(body, negotiated)
            elif url.path == "/ucp/checkout/confirm":
                self._checkout_confirm(body, negotiated)
            else:
                self._send({"error": "unknown path"}, status=404)

        # --------------------------------------------------------- handlers

        def _catalog_search(self, query, negotiated):
            if CATALOG_SEARCH not in negotiated:
                self._send({"error": f"capability {CATALOG_SEARCH} not negotiated"},
                           status=400, negotiated=negotiated)
                return
            q = (query.get("q", [""])[0])
            products = state.adapter.search_products(q)
            self._send({"result": {"items": [_product_json(p) for p in products],
                                   "count": len(products)}},
                       negotiated=negotiated)

        def _catalog_lookup(self, query, negotiated):
            if CATALOG_LOOKUP not in negotiated:
                self._send({"error": f"capability {CATALOG_LOOKUP} not negotiated"},
                           status=400, negotiated=negotiated)
                return
            pid = query.get("id", [""])[0]
            qty = int(query.get("quantity", ["1"])[0])
            variant = query.get("variant", [None])[0]
            try:
                product = state.adapter.get_product(pid)
                offer = state.adapter.get_offer(pid, qty, variant)
            except KeyError as exc:
                self._send({"error": str(exc)}, status=404, negotiated=negotiated)
                return

            result = {"item": _product_json(product),
                      "offer": offer.model_dump(mode="json")}

            # THE PRODUCT, in one if-statement: the extension block exists
            # only when negotiation kept org.bondlayer.benefit_value alive.
            # No special baseline path — the protocol prunes it.
            if BENEFIT_VALUE in negotiated:
                quote = loyalty.value_cards(self._member(), offer.total_cents,
                                            product.category)
                result["extensions"] = {BENEFIT_VALUE: {
                    "issuer": loyalty.MERCHANT_ID,
                    "signing_public_key": loyalty.PUBLIC_KEY_HEX,
                    "cards": [c.model_dump(mode="json") for c in loyalty.CARDS],
                    "valuation": quote.model_dump(mode="json"),
                }}
            self._send({"result": result}, negotiated=negotiated)

        def _identity_link(self, body, negotiated):
            if IDENTITY_LINKING not in negotiated:
                self._send({"error": f"capability {IDENTITY_LINKING} not negotiated"},
                           status=400, negotiated=negotiated)
                return
            # Stand-in for UCP identity linking's OAuth 2.0 account link:
            # in production this token comes out of an OAuth flow, not an
            # email lookup.
            member = loyalty.find_member(body.get("email", ""))
            if member is None:
                self._send({"result": {"linked": False}}, negotiated=negotiated)
                return
            token = f"link_{uuid.uuid4().hex[:16]}"
            state.links[token] = member
            log_event("member_identified", email=member.email,
                      tier=member.tier.value, via="ucp_identity_link")
            self._send({"result": {"linked": True, "link_token": token,
                                   "member": member.model_dump(mode="json")}},
                       negotiated=negotiated)

        def _checkout(self, body, negotiated):
            if CHECKOUT not in negotiated:
                self._send({"error": f"capability {CHECKOUT} not negotiated"},
                           status=400, negotiated=negotiated)
                return
            with state.lock:
                out = self._service().create_order(
                    body.get("items", []), body.get("idempotency_key", ""))
            status = 400 if "error" in out else 200
            self._send({"result": out}, status=status, negotiated=negotiated)

        def _checkout_confirm(self, body, negotiated):
            if CHECKOUT not in negotiated:
                self._send({"error": f"capability {CHECKOUT} not negotiated"},
                           status=400, negotiated=negotiated)
                return
            with state.lock:
                out = self._service().confirm_order(body.get("order_id", ""))
            status = 400 if "error" in out else 200
            self._send({"result": out}, status=status, negotiated=negotiated)

    return UCPHandler


def serve_in_thread(adapter: MockStoreAdapter,
                    port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    """Start the UCP head on a daemon thread (used by demo_ucp.py)."""
    state = _UCPState(adapter)
    server = ThreadingHTTPServer(("127.0.0.1", port), _make_handler(state))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    log_event("server_start", transport="ucp_http", port=port)
    print(f"UCP head (draft-style) on http://127.0.0.1:{port}", file=sys.stderr)
    print(f"  try: curl -s http://127.0.0.1:{port}/.well-known/ucp", file=sys.stderr)
    state = _UCPState(MockStoreAdapter())
    ThreadingHTTPServer(("127.0.0.1", port), _make_handler(state)).serve_forever()


if __name__ == "__main__":
    main()
