"""ShopifyStoreAdapter — ROADMAP STUB, deliberately not implemented in v1.

This is the seam that makes AgentBridge production-ready later: the MCP
server is written purely against `StoreAdapter`, so swapping
`MockStoreAdapter()` for `ShopifyStoreAdapter(shop, token)` is a one-line
change in server.py. Each method below documents the exact Shopify Admin
API call it maps to.

Auth: Admin API access token via `X-Shopify-Access-Token` header against
`https://{shop}.myshopify.com/admin/api/2024-10/...`.
"""

from __future__ import annotations

from typing import Optional

from agentbridge.adapters.base import StoreAdapter
from agentbridge.models import Offer, Order, OrderItem, Policy, Product

_MSG = "ShopifyStoreAdapter is a v2 roadmap item — use MockStoreAdapter for the demo"


class ShopifyStoreAdapter(StoreAdapter):
    def __init__(self, shop_domain: str, access_token: str) -> None:
        self.shop_domain = shop_domain
        self.access_token = access_token

    def search_products(self, query: str) -> list[Product]:
        # Maps to: GET /admin/api/2024-10/products.json?title={query}
        # (or the GraphQL Admin API `products(query: ...)` for real full-text search).
        raise NotImplementedError(_MSG)

    def get_product(self, product_id: str) -> Product:
        # Maps to: GET /admin/api/2024-10/products/{product_id}.json
        raise NotImplementedError(_MSG)

    def get_offer(self, product_id: str, quantity: int,
                  variant_id: Optional[str] = None) -> Offer:
        # Maps to: GET /admin/api/2024-10/variants/{variant_id}.json (price)
        #        + GET /admin/api/2024-10/inventory_levels.json?inventory_item_ids=...
        # Availability confidence derives from inventory_levels across locations.
        raise NotImplementedError(_MSG)

    def create_order(self, items: list[OrderItem], idempotency_key: str) -> Order:
        # Maps to: POST /admin/api/2024-10/draft_orders.json  (PENDING == draft order)
        # Idempotency: persist idempotency_key -> draft_order.id locally (sqlite),
        # since Shopify draft orders have no native idempotency-key support.
        raise NotImplementedError(_MSG)

    def confirm_order(self, order_id: str) -> Order:
        # Maps to: PUT /admin/api/2024-10/draft_orders/{id}/complete.json
        # (converts the draft to a real order; payment via Shopify's checkout
        # or a payment_pending completion — still gated behind this one call).
        raise NotImplementedError(_MSG)

    def get_policy(self, topic: str) -> Policy:
        # Maps to: GET /admin/api/2024-10/policies.json
        # (returns refund_policy, shipping_policy, etc. as structured objects).
        raise NotImplementedError(_MSG)
