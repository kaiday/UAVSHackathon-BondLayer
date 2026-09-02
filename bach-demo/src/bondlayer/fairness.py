"""Is the comparison rigged in Alpine's favour? Answered, rather than asserted.

The obvious objection to the demo is that Alpine wins because we gave Alpine
benefits and gave its competitors none. That objection was *correct* until the
competitors got policy documents: `data/merchants/peak/policy.md` and
`ridgeway/policy.md` now describe genuine, competitive terms.

Neither reaches the agent, because neither merchant runs BondLayer. So the demo
stops claiming Alpine is a better merchant and starts showing something
narrower and truer:

    Peak has $9.95 of delivery value it cannot put on the wire.
    Ridgeway has a warranty it can put on the wire but cannot sign.
    Alpine has the same kind of value, published and verifiable.

The gap is legibility, not merit — and that is a claim about our protocol, not
about our merchants.

`policy_facts.json` beside each policy is hand-extracted for this comparison.
It is never served by a merchant service and never reaches the agent; the
loader below refuses to read it from anywhere but disk for exactly that reason.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MERCHANT_DATA = ROOT / "data" / "merchants"


@dataclass
class StrandedValue:
    """What a merchant offers that an agent cannot read."""

    merchant_id: str
    has_policy_document: bool
    facts: list[dict[str, Any]] = field(default_factory=list)
    total_aud: float = 0.0
    published_machine_readable: int = 0
    signed: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "merchant_id": self.merchant_id,
            "has_policy_document": self.has_policy_document,
            "facts": self.facts,
            "total_aud": self.total_aud,
            "published_machine_readable": self.published_machine_readable,
            "signed": self.signed,
        }


def policy_prose(merchant_id: str) -> str | None:
    path = MERCHANT_DATA / merchant_id / "policy.md"
    return path.read_text(encoding="utf-8") if path.exists() else None


def stranded(merchant_id: str, *, published: int = 0, signed: int = 0) -> StrandedValue:
    """Value described in the merchant's own policy prose.

    `published` and `signed` come from what the merchant actually served over
    UCP, so the caller supplies them rather than this module guessing.
    """
    facts_path = MERCHANT_DATA / merchant_id / "policy_facts.json"
    prose = policy_prose(merchant_id)

    facts: list[dict[str, Any]] = []
    if facts_path.exists():
        blob = json.loads(facts_path.read_text(encoding="utf-8"))
        facts = blob.get("facts", [])

    return StrandedValue(
        merchant_id=merchant_id,
        has_policy_document=prose is not None,
        facts=facts,
        total_aud=round(sum(float(f.get("value_aud") or 0.0) for f in facts), 2),
        published_machine_readable=published,
        signed=signed,
    )


def summary(published_by_merchant: dict[str, tuple[int, int]]) -> dict[str, Any]:
    """One row per merchant: what it offers, what it published, what it signed.

    `published_by_merchant` maps merchant_id -> (records published, records
    signed), measured from the live UCP responses.
    """
    rows = []
    for mid, (published, signed) in published_by_merchant.items():
        s = stranded(mid, published=published, signed=signed)
        rows.append(s.as_dict())
    return {
        "merchants": rows,
        "note": (
            "Every merchant here has a real policy document written for humans. "
            "The difference on the wire is not what they offer — it is whether "
            "an agent can read it and whether they can prove it."
        ),
    }
