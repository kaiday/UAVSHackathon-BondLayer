"""The information gap, measured rather than narrated (demo-flow-v2 §3a).

The old headline was "the agent changed its pick". That claim rests entirely on
one model's judgement, and the first live recording showed the model declining
to change it (D9.14). This module computes what is true regardless of how any
model ranks: *what the agent could see*.

Every number here is derived from the exact payload the agent sent, so nothing
on the screen is a literal someone typed into the HTML.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from .agent.trv import Valuation
from .schema import Offer
from .signing import KeyRing

#: The merchant whose console the demo shows. The gap is asymmetric by design:
#: it is Alpine's data that capability negotiation withholds.
FOCUS_MERCHANT = "alpine"


@dataclass
class Visibility:
    """What one merchant's offer looked like to the agent, in four numbers."""

    fields_visible: int
    offer_legible_pct: float
    verified_value_aud: float
    benefits_withheld: int
    benefits_delivered: int
    benefits_published: int

    def as_dict(self) -> dict[str, float | int]:
        return asdict(self)


def _count_claims(node: object) -> int:
    """Machine-readable claims the agent was handed about this offer.

    Counting top-level keys instead would report 6 -> 8, which is true and
    useless: `published_benefits` is one key whether it carries one record or
    twenty. What changes under negotiation is the number of separate facts the
    agent can reason about, so that is what this counts -- every scalar leaf,
    with a list counted once because it is one claim ("sizes S-XL"), not five.
    """
    if isinstance(node, dict):
        return sum(_count_claims(v) for v in node.values())
    if isinstance(node, list):
        if all(not isinstance(v, (dict, list)) for v in node):
            return 1
        return sum(_count_claims(v) for v in node)
    return 1


def published_benefit_count(services: dict, merchant_id: str = FOCUS_MERCHANT) -> int:
    """How many benefit records the merchant holds, before negotiation prunes.

    Read off the live service rather than hardcoded, so adding a benefit to the
    scenario moves the number on the screen without anyone remembering to.
    """
    service = services.get(merchant_id)
    if service is None or not getattr(service, "benefits", None):
        return 0
    return max((len(recs) for recs in service.benefits.values()), default=0)


def measure(
    payload: str,
    offers: list[Offer],
    keyring: KeyRing,
    *,
    benefits_published: int,
    valuations: list[Valuation] | None = None,
    merchant_id: str = FOCUS_MERCHANT,
) -> Visibility:
    """Derive the four metrics from the payload that actually went to the model.

    `payload` is the string returned by `shopping_agent.build_rank_payload`, so
    `fields_visible` counts what the model was handed, not what we intended to
    hand it.
    """
    body = json.loads(payload)
    entry = next(
        (o for o in body.get("offers", []) if o.get("merchant_id") == merchant_id),
        None,
    )
    fields_visible = _count_claims(entry) if entry else 0

    offer = next((o for o in offers if o.merchant_id == merchant_id), None)
    delivered = len(offer.benefits) if offer and offer.benefits else 0

    legible = (delivered / benefits_published * 100.0) if benefits_published else 0.0

    verified_value = 0.0
    if valuations:
        val = next(
            (v for v in valuations if v.offer.merchant_id == merchant_id), None
        )
        if val is not None:
            # Only lines that reduce cost AND carry a verified signature count.
            # A provisional line is a forecast and an unverified one is never
            # valued at all, so neither belongs in a number labelled "verified".
            verified_value = round(
                -sum(
                    line.amount_aud
                    for line in val.lines
                    if line.amount_aud < 0 and line.status == "signed"
                ),
                2,
            )

    return Visibility(
        fields_visible=fields_visible,
        offer_legible_pct=round(legible, 1),
        verified_value_aud=verified_value,
        benefits_withheld=max(benefits_published - delivered, 0),
        benefits_delivered=delivered,
        benefits_published=benefits_published,
    )
