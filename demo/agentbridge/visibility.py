"""The information-gap metrics — derived from the exact payload the agent
received, never asserted. These are the merchant console's headline
numbers: what could the agent see, how much of the real offer was
legible, how much verified value was creditable, and what was withheld
by the wire.
"""

from __future__ import annotations

from typing import Any

from agentbridge import loyalty
from agentbridge.models import OfferCard
from agentbridge.ucp import BENEFIT_VALUE


def count_leaf_fields(obj: Any) -> int:
    """How many concrete data points the payload carries."""
    if isinstance(obj, dict):
        return sum(count_leaf_fields(v) for v in obj.values())
    if isinstance(obj, list):
        return sum(count_leaf_fields(v) for v in obj)
    return 1


def metrics(merchant_payload: dict, member_email: str | None = "ava@example.com",
            total_real_benefits: int | None = None) -> dict:
    """Derive the four console figures from one merchant's payload.

    `total_real_benefits` is what the merchant actually funds (defaults
    to the built-in card catalogue) — the denominator for legibility.
    """
    total_real = total_real_benefits if total_real_benefits is not None \
        else len(loyalty.CARDS)
    block = (merchant_payload.get("extensions") or {}).get(BENEFIT_VALUE)
    records = (block or {}).get("benefit_records") or (block or {}).get("cards") or []

    verified_value = 0
    if records:
        member = loyalty.find_member(member_email) if member_email else None
        cards = [OfferCard(**{k: v for k, v in r.items()
                              if k not in ("verified", "verification")})
                 for r in records]
        list_total = (merchant_payload.get("offer") or {}).get("total_cents", 0)
        category = (merchant_payload.get("item") or {}).get("category")
        quote = loyalty.value_cards(member, list_total, category, cards=cards)
        verified_value = quote.price_credit_cents + quote.comparison_value_cents

    visible = len(records)
    return {
        "fields_visible": count_leaf_fields(merchant_payload),
        "benefits_on_wire": visible,
        "benefits_total": total_real,
        "legible_pct": round(100 * visible / total_real) if total_real else 0,
        "verified_value_cents": verified_value,
        "benefits_withheld": total_real - visible,
    }
