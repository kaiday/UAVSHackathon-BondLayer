"""Who a merchant says a shopper is.

The merchant is the authority on its own membership. An agent sends an id and
this module answers from the merchant's roster; it never takes the agent's word
for a status or a tier. That asymmetry is the whole point -- ``member_price``
records are worth real money, so if an agent could assert ``tier: plus`` on the
wire it could assert its way into a discount, and the comparison would be
measuring what agents claim rather than what merchants owe.

Membership is per-merchant and there is no global roster: the same shopper is a
Circle member at Voltway and a stranger at NorthGear.

**Consent is structural.** Nothing here filters a shopper out after the fact.
An agent that withholds consent simply never sends an id, so
:func:`resolve_shopper` is never asked and the records scoped to that shopper
are never *selected* (see ``records.for_sku``). There is no ``if consent:``
branch anywhere to trust or to get wrong.

This module only says what the merchant attests. What that attestation is
*worth* is the agent's call, and it lives agent-side in
``valuation.reference_policy.attested_conditions`` -- the merchant states a
fact about its own roster, and the shopper's own policy decides what the fact
unlocks.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[3] / "data"
ROSTERS = DATA / "membership" / "rosters.json"

#: What an unidentified request gets back. ``linked: False`` is a normal
#: answer, not an error: most shoppers are not members of most merchants.
NOT_LINKED = {"linked": False, "reason": "no linked shopper"}


def load_rosters(path: Path = ROSTERS) -> dict[str, dict]:
    """Every merchant's roster, or ``{}`` when none is published.

    An absent file is a normal state, mirroring ``records.load_records``: a
    merchant that runs no membership programme has no roster, and a fresh clone
    that has not been seeded has no file.
    """
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    rosters = payload.get("rosters", payload) if isinstance(payload, dict) else {}
    return {
        mid: dict(entries)
        for mid, entries in rosters.items()
        if isinstance(entries, dict)
    }


def resolve_shopper(
    rosters: dict[str, dict], merchant_id: str, shopper_id: str | None
) -> dict:
    """What ``merchant_id`` says about ``shopper_id``.

    An id the roster does not carry resolves to :data:`NOT_LINKED`, exactly as
    no id at all does. An agent cannot assert its way into a tier because the
    only thing it gets to supply is the id itself.
    """
    if not shopper_id:
        return dict(NOT_LINKED)
    entry = rosters.get(merchant_id, {}).get(shopper_id)
    if entry is None:
        return {"linked": False, "reason": f"{shopper_id!r} is not a member here"}
    return {
        "linked": True,
        "shopper_id": shopper_id,
        "status": entry.get("status"),
        "tier": entry.get("tier"),
        "orders": entry.get("orders"),
    }
