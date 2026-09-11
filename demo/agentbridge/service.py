"""AgentBridgeService — the tool implementations behind the MCP server.

One class, eight methods, mirroring the eight MCP tools 1:1. Both the MCP
server (server.py) and the benchmark's Run B drive *these exact
functions*, so the benchmark measures the same logic Claude Desktop
uses. Every call emits a structured log event and returns plain
JSON-safe dicts (validated through the Pydantic models on the way out).

The loyalty layer (agentbridge.loyalty) plugs in here, NOT in the store
adapter: membership and signed Offer Cards are a merchant-side layer
riding on top of whatever backend the adapter wraps — which is the whole
architectural pitch.
"""

from __future__ import annotations

from typing import Any, Optional

from agentbridge import loyalty
from agentbridge.adapters.base import StoreAdapter
from agentbridge.logging_config import log_event
from agentbridge.models import Member, OrderItem, cents_to_str


class AgentBridgeService:
    def __init__(self, adapter: StoreAdapter) -> None:
        self.adapter = adapter
        # The member this agent session is shopping for (set by
        # identify_member / enroll_member; colours every later quote).
        self.member: Optional[Member] = None

    # ------------------------------------------------------------------ tools

    def search_products(self, query: str = "") -> dict[str, Any]:
        log_event("tool_call", tool="search_products", query=query)
        products = self.adapter.search_products(query)
        results = []
        for p in products:
            results.append({
                "product_id": p.product_id,
                "title": p.title,
                "description": p.description,
                "category": p.category,
                "price_cents": p.price_cents,
                "price": cents_to_str(p.price_cents, p.currency),
                "in_stock": p.in_stock,
                "delivery_sla_days": p.delivery_sla_days,
                "variants": [
                    {"variant_id": v.variant_id, "size": v.size,
                     "color": v.color, "stock": v.stock}
                    for v in p.variants
                ],
            })
        return {"count": len(results), "products": results}

    def get_offer(self, product_id: str, quantity: int = 1,
                  variant_id: Optional[str] = None) -> dict[str, Any]:
        log_event("tool_call", tool="get_offer", product_id=product_id,
                  quantity=quantity, variant_id=variant_id,
                  member=self.member.email if self.member else None)
        try:
            offer = self.adapter.get_offer(product_id, quantity, variant_id)
            product = self.adapter.get_product(product_id)
        except KeyError as exc:
            return {"error": str(exc)}
        data = offer.model_dump(mode="json")
        data["total"] = cents_to_str(offer.total_cents, offer.currency)
        data["unit_price"] = cents_to_str(offer.unit_price_cents, offer.currency)

        # Attach the loyalty quote: signed Offer Cards valued deterministically
        # for this member and basket. Rank on effective_cost, not list price.
        quote = loyalty.value_cards(self.member, offer.total_cents, product.category)
        data["loyalty"] = quote.model_dump(mode="json")
        data["loyalty"]["merchant_public_key"] = loyalty.PUBLIC_KEY_HEX
        data["effective_cost"] = cents_to_str(quote.effective_cost_cents)
        data["payable_total"] = cents_to_str(quote.payable_total_cents)
        return data

    def identify_member(self, email: str) -> dict[str, Any]:
        log_event("tool_call", tool="identify_member", email=email)
        member = loyalty.find_member(email)
        if member is None:
            return {
                "found": False,
                "message": f"No membership found for {email}. You can enrol "
                           "the shopper with enroll_member — but ONLY after "
                           "they explicitly agree to join.",
            }
        self.member = member
        log_event("member_identified", email=member.email, tier=member.tier.value)
        return {"found": True, "member": member.model_dump(mode="json"),
                "message": "Member recognised. Offers from get_offer now "
                           "include member pricing and effective cost."}

    def enroll_member(self, email: str, name: str = "",
                      consent: bool = False) -> dict[str, Any]:
        log_event("tool_call", tool="enroll_member", email=email, consent=consent)
        # --- CONSENT GATE: enrolment never happens implicitly. ---
        if not consent:
            return {"error": "Enrolment requires explicit consent. Ask the "
                             "shopper whether they want to join the loyalty "
                             "program, and pass consent=true only if they "
                             "clearly agree."}
        if "@" not in email:
            return {"error": f"'{email}' does not look like an email address."}
        self.member = loyalty.enroll(email, name)
        return {"member": self.member.model_dump(mode="json"),
                "message": "Enrolled (BRONZE tier). Member pricing applies to "
                           "this purchase — quotes from get_offer now show it."}

    def create_order(self, items: list[dict[str, Any]],
                     idempotency_key: str) -> dict[str, Any]:
        log_event("tool_call", tool="create_order", items=items,
                  idempotency_key=idempotency_key)
        try:
            order_items = [OrderItem(**item) for item in items]
            order = self.adapter.create_order(order_items, idempotency_key)
        except (KeyError, ValueError) as exc:
            return {"error": str(exc)}

        # Apply the member's verified price credit so the amount that settles
        # IS the member price — "the offer that won is the offer delivered".
        # Guard: an idempotent replay returns the already-discounted order
        # (list_total_cents set), which must never be discounted twice.
        if self.member is not None and order.list_total_cents is None:
            category = self.adapter.get_product(order.items[0].product_id).category
            quote = loyalty.value_cards(self.member, order.total_cents, category)
            order.member_email = self.member.email
            order.list_total_cents = order.total_cents
            order.loyalty_credit_cents = quote.price_credit_cents
            order.total_cents -= quote.price_credit_cents
            log_event("loyalty_credited", order_id=order.order_id,
                      member=self.member.email,
                      credit_cents=order.loyalty_credit_cents,
                      settle_cents=order.total_cents)

        note = ("Order is PENDING — no payment has been taken. "
                "Call confirm_order to complete the purchase.")
        if order.loyalty_credit_cents:
            note = (f"Member credit of {cents_to_str(order.loyalty_credit_cents)} "
                    f"applied for {order.member_email}: "
                    f"{cents_to_str(order.list_total_cents)} list -> "
                    f"{cents_to_str(order.total_cents)} to charge. " + note)
        return self._order_dict(order) | {"note": note}

    def confirm_order(self, order_id: str) -> dict[str, Any]:
        log_event("tool_call", tool="confirm_order", order_id=order_id)
        try:
            order = self.adapter.confirm_order(order_id)
        except (KeyError, ValueError) as exc:
            return {"error": str(exc)}
        return self._order_dict(order) | {
            "note": "Order confirmed. Payment settled in TEST MODE "
                    f"(ref {order.payment_ref}).",
        }

    def get_return_policy(self) -> dict[str, Any]:
        log_event("tool_call", tool="get_return_policy")
        return self.adapter.get_policy("returns").model_dump()

    def get_shipping_info(self) -> dict[str, Any]:
        log_event("tool_call", tool="get_shipping_info")
        return self.adapter.get_policy("shipping").model_dump()

    # -------------------------------------------------------------- internals

    @staticmethod
    def _order_dict(order) -> dict[str, Any]:
        data = order.model_dump(mode="json")
        data["total"] = cents_to_str(order.total_cents, order.currency)
        return data
