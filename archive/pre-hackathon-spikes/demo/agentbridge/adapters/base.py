"""StoreAdapter — the abstract interface every store backend implements.

AgentBridge's MCP tools are written against this interface only, so
plugging in a real backend (Shopify, WooCommerce, a custom API) means
implementing these six methods and nothing else.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from agentbridge.models import Offer, Order, OrderItem, Policy, Product


class StoreAdapter(ABC):
    """Abstract store backend.

    Contract notes:
    - `create_order` MUST be idempotent on `idempotency_key` and MUST NOT
      move money — it returns a PENDING order.
    - `confirm_order` is the single settlement gate: only here does a
      (test-mode) charge happen and the order become CONFIRMED.
    """

    @abstractmethod
    def search_products(self, query: str) -> list[Product]:
        """Full-text search over the catalogue. Empty query returns everything."""

    @abstractmethod
    def get_product(self, product_id: str) -> Product:
        """Fetch one product by id. Raises KeyError if unknown."""

    @abstractmethod
    def get_offer(
        self, product_id: str, quantity: int, variant_id: Optional[str] = None
    ) -> Offer:
        """Quote a concrete offer (price, availability, SLA, return terms)."""

    @abstractmethod
    def create_order(self, items: list[OrderItem], idempotency_key: str) -> Order:
        """Create a PENDING order. Same idempotency_key -> same order, never a duplicate."""

    @abstractmethod
    def confirm_order(self, order_id: str) -> Order:
        """Explicit confirmation gate: settle (test mode) and mark CONFIRMED."""

    @abstractmethod
    def get_policy(self, topic: str) -> Policy:
        """Return a store policy. Topics: 'returns', 'shipping'."""
