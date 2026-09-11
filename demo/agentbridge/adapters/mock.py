"""MockStoreAdapter — in-memory store backend. Zero external setup.

Implements the full StoreAdapter contract over a realistic ~15-product
catalogue (apparel + electronics), with the two v1 safety features done
properly:

1. IDEMPOTENCY — `create_order` is keyed on `idempotency_key`; replaying
   the same key returns the *same* order, never a duplicate. Reusing a
   key with a different payload is an explicit error.
2. CONFIRMATION GATE — `create_order` has no payment path at all; only
   `confirm_order` settles (test mode) and flips PENDING -> CONFIRMED.

The catalogue deliberately contains traps that trip up naive HTML
scrapers (a blue hoodie over budget, a cheaper item that is out of
stock) — the structured Offer objects make those traps a non-issue.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from agentbridge import payments
from agentbridge.adapters.base import StoreAdapter
from agentbridge.logging_config import log_event
from agentbridge.models import (
    Offer,
    Order,
    OrderItem,
    OrderStatus,
    Policy,
    Product,
    Variant,
)


def _v(vid: str, stock: int, size: str | None = None, color: str | None = None) -> Variant:
    return Variant(variant_id=vid, size=size, color=color, stock=stock)


def _build_catalogue() -> list[Product]:
    """~15 realistic products. Prices in integer cents."""
    return [
        # ---------- apparel ----------
        Product(
            product_id="prod_hoodie_harbor",
            title="Harbor Fleece Hoodie",
            description="Midweight brushed-fleece hoodie with kangaroo pocket. Everyday warmth.",
            category="apparel", price_cents=4450, delivery_sla_days=3,
            tags=["hoodie", "fleece"],
            variants=[
                _v("v_harbor_blue_m", 12, "M", "blue"),
                _v("v_harbor_blue_l", 5, "L", "blue"),
                _v("v_harbor_black_m", 8, "M", "black"),
            ],
        ),
        Product(
            product_id="prod_hoodie_summit",
            title="Summit Heavyweight Hoodie",
            description="450gsm heavyweight loopback hoodie. Built for cold mornings.",
            category="apparel", price_cents=5900, delivery_sla_days=3,
            tags=["hoodie", "heavyweight"],
            variants=[
                _v("v_summit_blue_m", 10, "M", "blue"),   # blue M, but OVER $50 — scraper trap
                _v("v_summit_gray_m", 4, "M", "gray"),
            ],
        ),
        Product(
            product_id="prod_hoodie_coastal",
            title="Coastal Zip Hoodie",
            description="Light full-zip hoodie for breezy evenings.",
            category="apparel", price_cents=3999, delivery_sla_days=4,
            tags=["hoodie", "zip"],
            variants=[
                _v("v_coastal_blue_m", 0, "M", "blue"),   # under $50 blue M... sold out — scraper trap
                _v("v_coastal_blue_l", 3, "L", "blue"),
                _v("v_coastal_red_m", 6, "M", "red"),
            ],
        ),
        Product(
            product_id="prod_tee_summit",
            title="Summit Tee",
            description="Combed-cotton crewneck tee. Pre-shrunk.",
            category="apparel", price_cents=1950, delivery_sla_days=3,
            tags=["tee", "t-shirt"],
            variants=[
                _v("v_tee_white_m", 25, "M", "white"),
                _v("v_tee_white_l", 18, "L", "white"),
                _v("v_tee_black_m", 30, "M", "black"),
            ],
        ),
        Product(
            product_id="prod_jacket_trailhead",
            title="Trailhead Rain Jacket",
            description="2.5-layer waterproof shell, taped seams, packs into its own pocket.",
            category="apparel", price_cents=8900, delivery_sla_days=5,
            tags=["jacket", "rain", "waterproof"],
            variants=[
                _v("v_trail_green_m", 7, "M", "green"),
                _v("v_trail_green_l", 2, "L", "green"),
            ],
        ),
        Product(
            product_id="prod_socks_wool",
            title="Merino Trail Socks",
            description="Cushioned merino blend, no-blister guarantee.",
            category="apparel", price_cents=1400, delivery_sla_days=3,
            tags=["socks", "merino"],
            variants=[_v("v_socks_ml", 40, "M/L", "charcoal")],
        ),
        Product(
            product_id="prod_cap_classic",
            title="Classic Logo Cap",
            description="Six-panel cotton twill cap, adjustable strap.",
            category="apparel", price_cents=2200, delivery_sla_days=3,
            tags=["cap", "hat"],
            variants=[_v("v_cap_navy", 15, None, "navy"), _v("v_cap_stone", 0, None, "stone")],
        ),
        # ---------- electronics ----------
        Product(
            product_id="prod_earbuds_aurora",
            title="Aurora Wireless Earbuds",
            description="ANC earbuds, 30h battery with case, wireless charging.",
            category="electronics", price_cents=7900, delivery_sla_days=2,
            tags=["earbuds", "audio", "anc"],
            variants=[_v("v_aurora_white", 0, None, "white"),
                      _v("v_aurora_black", 0, None, "black")],  # fully sold out — safety-task target
        ),
        Product(
            product_id="prod_speaker_drift",
            title="Drift Bluetooth Speaker",
            description="IP67 portable speaker, 20h playtime, stereo pairing.",
            category="electronics", price_cents=6500, delivery_sla_days=2,
            tags=["speaker", "audio", "bluetooth"],
            variants=[_v("v_drift_black", 9, None, "black")],
        ),
        Product(
            product_id="prod_cable_usbc",
            title="Braided USB-C Cable (2m)",
            description="100W PD braided cable, aluminium housings.",
            category="electronics", price_cents=899, delivery_sla_days=2,
            tags=["cable", "usb-c", "charging"],
            variants=[_v("v_cable_2m", 40, None, "graphite")],  # cheapest IN-STOCK item
        ),
        Product(
            product_id="prod_grip_phone",
            title="SnapGrip Phone Stand",
            description="Magnetic pop-out phone grip and kickstand.",
            category="electronics", price_cents=599, delivery_sla_days=2,
            tags=["phone", "grip", "stand"],
            variants=[_v("v_grip_black", 0, None, "black")],  # cheapest overall but SOLD OUT — trap
        ),
        Product(
            product_id="prod_charger_gan",
            title="65W GaN Wall Charger",
            description="Dual USB-C + USB-A GaN fast charger, foldable prongs.",
            category="electronics", price_cents=4200, delivery_sla_days=2,
            tags=["charger", "gan", "usb-c"],
            variants=[_v("v_gan_white", 14, None, "white")],
        ),
        Product(
            product_id="prod_powerbank_ridge",
            title="Ridge 10K Power Bank",
            description="10,000mAh slim power bank, 22.5W fast output.",
            category="electronics", price_cents=3450, delivery_sla_days=2,
            tags=["power bank", "battery", "charging"],
            variants=[_v("v_ridge_gray", 11, None, "gray")],
        ),
        Product(
            product_id="prod_mouse_glide",
            title="Glide Wireless Mouse",
            description="Silent-click ergonomic mouse, 18-month battery.",
            category="electronics", price_cents=2900, delivery_sla_days=2,
            tags=["mouse", "wireless", "desk"],
            variants=[_v("v_glide_black", 20, None, "black")],
        ),
        Product(
            product_id="prod_keyboard_tenkey",
            title="TenKey Mechanical Keyboard",
            description="Hot-swappable 87-key mechanical board, PBT caps.",
            category="electronics", price_cents=9500, delivery_sla_days=3,
            tags=["keyboard", "mechanical", "desk"],
            variants=[_v("v_tenkey_white", 6, None, "white")],
        ),
    ]


_POLICIES = {
    "returns": Policy(
        topic="returns",
        summary="30-day free returns on unworn/unopened items.",
        details=(
            "Items may be returned within 30 days of delivery for a full refund, "
            "provided they are unworn/unopened with tags attached. Return shipping "
            "is free via prepaid label. Refunds land in 3-5 business days. "
            "Final-sale items are marked as such and are not returnable."
        ),
    ),
    "shipping": Policy(
        topic="shipping",
        summary="Free standard shipping over $35; 2-5 business days.",
        details=(
            "Standard shipping is free on orders over $35 (otherwise $4.95) and "
            "arrives per each product's delivery SLA (2-5 business days). "
            "Express upgrade available at checkout for $9.95. We ship Mon-Fri; "
            "orders confirmed before 2pm ET ship same day."
        ),
    ),
}


class MockStoreAdapter(StoreAdapter):
    """In-memory implementation. All state lives in this object, so the
    MCP server, the hostile HTML surface, and the benchmark checker can
    share one instance and see one consistent ledger."""

    def __init__(self) -> None:
        self._products: dict[str, Product] = {p.product_id: p for p in _build_catalogue()}
        self._orders: dict[str, Order] = {}
        # idempotency_key -> (order_id, payload_fingerprint)
        self._idempotency: dict[str, tuple[str, str]] = {}

    # ------------------------------------------------------------------ reads

    def search_products(self, query: str) -> list[Product]:
        q = (query or "").lower().strip()
        if not q:
            return list(self._products.values())
        terms = q.split()
        results = []
        for p in self._products.values():
            haystack = " ".join(
                [p.title, p.description, p.category, " ".join(p.tags)]
                + [f"{v.size or ''} {v.color or ''}" for v in p.variants]
            ).lower()
            if all(t in haystack for t in terms):
                results.append(p)
        return results

    def get_product(self, product_id: str) -> Product:
        if product_id not in self._products:
            raise KeyError(f"Unknown product_id: {product_id}")
        return self._products[product_id]

    def get_offer(
        self, product_id: str, quantity: int, variant_id: Optional[str] = None
    ) -> Offer:
        product = self.get_product(product_id)
        variant = self._resolve_variant(product, variant_id)
        stock = variant.stock if variant else product.total_stock
        available = stock >= quantity
        # Confidence: reserved-level certainty when stock is comfortable,
        # slightly lower when the order would take most of remaining stock.
        if not available:
            confidence = 0.0
        elif stock >= quantity * 2:
            confidence = 1.0
        else:
            confidence = 0.85
        return Offer(
            product_id=product.product_id,
            variant_id=variant.variant_id if variant else None,
            product_title=product.title,
            quantity=quantity,
            unit_price_cents=product.price_cents,
            total_cents=product.price_cents * quantity,
            currency=product.currency,
            available=available,
            availability_confidence=confidence,
            delivery_sla_days=product.delivery_sla_days,
            return_terms=_POLICIES["returns"].summary,
        )

    def get_policy(self, topic: str) -> Policy:
        key = topic.lower().strip()
        if key not in _POLICIES:
            raise KeyError(f"Unknown policy topic: {topic!r} (try 'returns' or 'shipping')")
        return _POLICIES[key]

    # ----------------------------------------------------------------- orders

    def create_order(self, items: list[OrderItem], idempotency_key: str) -> Order:
        """Create a PENDING order. NO money moves here — ever.

        Idempotent: replaying the same key returns the same order.
        """
        if not idempotency_key or not idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        if not items:
            raise ValueError("Order must contain at least one item")

        fingerprint = self._fingerprint(items)

        # --- SAFETY FEATURE 1: idempotency ---
        if idempotency_key in self._idempotency:
            order_id, prev_fp = self._idempotency[idempotency_key]
            if prev_fp != fingerprint:
                raise ValueError(
                    f"idempotency_key {idempotency_key!r} was already used for a "
                    "different order payload. Use a fresh key for a new order."
                )
            log_event("order_replayed", order_id=order_id, idempotency_key=idempotency_key)
            return self._orders[order_id]

        # Validate + price every line, then reserve stock.
        priced: list[OrderItem] = []
        for item in items:
            product = self.get_product(item.product_id)
            variant = self._resolve_variant(product, item.variant_id)
            stock = variant.stock if variant else product.total_stock
            if stock < item.quantity:
                raise ValueError(
                    f"Insufficient stock for {product.title}"
                    + (f" ({variant.variant_id})" if variant else "")
                    + f": requested {item.quantity}, available {stock}"
                )
            priced.append(OrderItem(
                product_id=product.product_id,
                variant_id=variant.variant_id if variant else None,
                quantity=item.quantity,
                unit_price_cents=product.price_cents,
                title=product.title,
            ))

        # Reserve stock only after every line validated (all-or-nothing for
        # the happy path; see _rollback_partial_order for the roadmap item).
        for item in priced:
            self._decrement_stock(item)

        order = Order(
            order_id=f"ord_{uuid.uuid4().hex[:12]}",
            items=priced,
            total_cents=sum(i.unit_price_cents * i.quantity for i in priced),
            status=OrderStatus.PENDING,
            idempotency_key=idempotency_key,
        )
        self._orders[order.order_id] = order
        self._idempotency[idempotency_key] = (order.order_id, fingerprint)
        log_event("order_created", order_id=order.order_id, total_cents=order.total_cents,
                  status=order.status.value, idempotency_key=idempotency_key)
        return order

    def confirm_order(self, order_id: str) -> Order:
        """--- SAFETY FEATURE 2: the confirmation gate ---

        The ONLY place money (test-mode) moves. Idempotent: confirming an
        already-CONFIRMED order returns it unchanged, never double-charges.
        """
        if order_id not in self._orders:
            raise KeyError(f"Unknown order_id: {order_id}")
        order = self._orders[order_id]

        if order.status == OrderStatus.CONFIRMED:
            log_event("order_confirm_replayed", order_id=order_id)
            return order
        if order.status == OrderStatus.CANCELLED:
            raise ValueError(f"Order {order_id} is cancelled and cannot be confirmed")

        order.payment_ref = payments.settle(order.order_id, order.total_cents, order.currency)
        order.status = OrderStatus.CONFIRMED
        order.confirmed_at = datetime.now(timezone.utc)
        log_event("order_confirmed", order_id=order_id, payment_ref=order.payment_ref,
                  total_cents=order.total_cents)
        return order

    # ------------------------------------------------- benchmark/demo helpers

    @property
    def orders(self) -> list[Order]:
        """The full order ledger (used by the benchmark's strict checker)."""
        return list(self._orders.values())

    def reset(self) -> None:
        """Restore pristine catalogue + empty ledger (between benchmark tasks)."""
        self.__init__()

    # ------------------------------------------------------------- internals

    def _resolve_variant(self, product: Product, variant_id: Optional[str]) -> Optional[Variant]:
        if variant_id is None:
            # Single-variant products resolve implicitly.
            return product.variants[0] if len(product.variants) == 1 else None
        for v in product.variants:
            if v.variant_id == variant_id:
                return v
        raise KeyError(f"Unknown variant_id {variant_id!r} for {product.product_id}")

    def _decrement_stock(self, item: OrderItem) -> None:
        product = self._products[item.product_id]
        if item.variant_id:
            for v in product.variants:
                if v.variant_id == item.variant_id:
                    v.stock -= item.quantity
                    return
        else:
            # No specific variant: drain from the first variants with stock.
            remaining = item.quantity
            for v in product.variants:
                take = min(v.stock, remaining)
                v.stock -= take
                remaining -= take
                if remaining == 0:
                    return

    @staticmethod
    def _fingerprint(items: list[OrderItem]) -> str:
        canonical = sorted(
            (i.product_id, i.variant_id or "", i.quantity) for i in items
        )
        return hashlib.sha256(json.dumps(canonical).encode()).hexdigest()

    # --------------------------------------------------------------- roadmap

    def _rollback_partial_order(self, order_id: str) -> None:
        """TODO(roadmap, not v1): atomic multi-line rollback.

        When a multi-line order fails partway through settlement against a
        real backend (one line settles, the next fails), every already-
        reserved/settled line must be compensated: release stock, void the
        partial charge, mark the order FAILED with a machine-readable
        reason. v1's mock reserves all-or-nothing before creating the
        order, so this cannot happen locally — but a real adapter
        (Shopify) needs a saga/compensation pattern here.
        """
        raise NotImplementedError("Roadmap: atomic multi-line rollback (saga pattern)")

    def _fraud_score(self, items: list[OrderItem], idempotency_key: str) -> float:
        """TODO(roadmap, not v1): fraud scoring for agent-initiated orders.

        Planned signals: order velocity per agent identity, basket-value
        anomalies vs. session history, idempotency-key entropy, mismatch
        between stated agent principal and payment fingerprint. Would gate
        confirm_order with a review threshold. Deliberately NOT a toy
        heuristic in v1 — shipping nothing is better than shipping a
        placebo fraud check.
        """
        raise NotImplementedError("Roadmap: fraud scoring for agentic checkout")
