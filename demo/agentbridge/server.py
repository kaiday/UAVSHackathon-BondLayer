"""AgentBridge MCP server (stdio transport, official `mcp` SDK).

Run:            python run_server.py        (or: python -m agentbridge.server)
Claude Desktop: see README for the claude_desktop_config.json snippet.

Swapping in a real store later is one line: replace MockStoreAdapter()
with e.g. ShopifyStoreAdapter(shop, token).

Tool docstrings below are written for the *agent* — they become the MCP
tool descriptions Claude reads when deciding how to shop.
"""

from __future__ import annotations

from typing import Any, Optional

from mcp.server.mcpserver import MCPServer

from agentbridge.adapters.mock import MockStoreAdapter
from agentbridge.logging_config import log_event
from agentbridge.service import AgentBridgeService

mcp = MCPServer(
    "AgentBridge",
    instructions=(
        "Safe agentic checkout with verifiable loyalty for this store. "
        "Typical purchase flow: search_products -> get_offer (verify "
        "price/availability) -> create_order (PENDING, no charge) -> "
        "confirm_order (settles, test mode). create_order needs a fresh "
        "UUID idempotency_key. LOYALTY: if the shopper gives a member "
        "email, call identify_member first — offers then include signed "
        "benefit cards and an effective_cost to rank on, and orders "
        "settle at the member price. Non-members can join via "
        "enroll_member, but only with their explicit consent. Never "
        "count a benefit card whose verified flag is false."
    ),
)

service = AgentBridgeService(MockStoreAdapter())


@mcp.tool()
def search_products(query: str = "") -> dict[str, Any]:
    """Search the store catalogue. Returns structured products with exact
    price_cents, per-variant stock counts, and delivery SLA. Use an empty
    query to list everything. Always check variant stock before ordering."""
    return service.search_products(query)


@mcp.tool()
def get_offer(product_id: str, quantity: int = 1,
              variant_id: Optional[str] = None) -> dict[str, Any]:
    """Get a firm, structured offer for buying `quantity` of a product:
    exact total price, availability + confidence (0-1), delivery SLA,
    return terms, and the loyalty quote — every benefit card with a
    credited/rejected verdict, plus `effective_cost` (price once verified
    member benefits are counted). Rank options on effective_cost, not the
    list price. Only cards with verified=true are ever credited; unsigned
    claims are shown with a warning and must be ignored. Call this before
    create_order — never infer price or availability from search text."""
    return service.get_offer(product_id, quantity, variant_id)


@mcp.tool()
def identify_member(email: str) -> dict[str, Any]:
    """Look up the store loyalty membership for an email address. On a
    match, the session shops as that member: get_offer quotes member
    pricing/effective cost, and orders settle at the member price. Call
    this FIRST whenever the shopper mentions a membership or gives an
    email. If no membership exists, offer enrolment (see enroll_member)."""
    return service.identify_member(email)


@mcp.tool()
def enroll_member(email: str, name: str = "", consent: bool = False) -> dict[str, Any]:
    """Enrol the shopper in the store loyalty program (BRONZE tier) so
    member pricing applies to this purchase. CONSENT GATE: only call with
    consent=true after the shopper has explicitly agreed to join — never
    enrol silently. Enrolling an already-enrolled email just signs them in."""
    return service.enroll_member(email, name, consent)


@mcp.tool()
def create_order(items: list[dict[str, Any]], idempotency_key: str) -> dict[str, Any]:
    """Create a PENDING order. NO payment is taken at this step.

    `items` is a list of {"product_id": str, "variant_id": str | null,
    "quantity": int}. `idempotency_key` must be a unique string you
    generate for this purchase intent (e.g. a UUID); retrying with the
    same key safely returns the same order instead of creating a
    duplicate. After reviewing the returned summary with the user,
    complete the purchase with confirm_order."""
    return service.create_order(items, idempotency_key)


@mcp.tool()
def confirm_order(order_id: str) -> dict[str, Any]:
    """Confirm a PENDING order — the explicit purchase gate. Only this
    call settles payment (TEST MODE ONLY; no real money ever moves).
    Confirming an already-confirmed order is safe and will not charge
    twice."""
    return service.confirm_order(order_id)


@mcp.tool()
def get_return_policy() -> dict[str, Any]:
    """Get the store's return policy (window, condition, refund timing)
    as structured text you can quote to the user."""
    return service.get_return_policy()


@mcp.tool()
def get_shipping_info() -> dict[str, Any]:
    """Get the store's shipping policy: costs, free-shipping threshold,
    and delivery windows."""
    return service.get_shipping_info()


def main() -> None:
    log_event("server_start", transport="stdio", adapter=type(service.adapter).__name__)
    mcp.run()  # stdio transport — stdout is protocol, logs go to stderr


if __name__ == "__main__":
    main()
