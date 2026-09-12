"""What the merchant lost, and to what — measured, not asserted.

Everything else in this demo answers "does BondLayer change the outcome of one
comparison?". A merchant does not renew a subscription for that. They renew for
the standing question:

    I lost. What did I lose to, and is any of it something I can fix?

So this module runs the ranking repeatedly in *both* capability states, tallies
how often the focus merchant is chosen, and — for every loss — names the
published benefits the agent was never handed and what the deterministic ledger
says each one was worth.

Three properties this had to have, or it would be decoration:

**Every row is derived.** The win/loss counts come from real ranking calls via
`agent.repeat`; the attribution lines come from `agent.trv`'s ledger for the
same offers. Nothing here is a figure anyone typed.

**A miss is reported, never counted.** `repeat` already excludes fallbacks from
its denominator, and a condition with no recorded runs reports zero
comparisons rather than an invented record.

**The recoverable figure is a ceiling, not a promise.** It is the sum of the
*signed* cost-reducing ledger lines the agent could not see — the same ceiling
discipline as `trv.value_offer`. Provisional and unverified lines are excluded,
because a number labelled "recoverable" must not include value we cannot prove.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .agent import repeat as rp
from .agent.policy import CustomerPolicy
from .agent.trv import Valuation
from .agent.trv import rank as trv_rank
from .schema import Offer
from .signing import KeyRing
from .visibility import FOCUS_MERCHANT


@dataclass
class ConditionResult:
    """One capability state, run `n` times."""

    extension: str
    comparisons: int
    won: int
    lost: int
    lost_to: dict[str, int] = field(default_factory=dict)
    headline: str = ""

    @property
    def win_rate_pct(self) -> float:
        return round(self.won / self.comparisons * 100.0, 1) if self.comparisons else 0.0


@dataclass
class LossReason:
    """One published benefit the agent never saw, and what it was worth."""

    title: str
    value_aud: float
    status: str
    published: bool
    reached_agent: bool


@dataclass
class Scoreboard:
    merchant_id: str
    off: ConditionResult
    on: ConditionResult
    reasons: list[LossReason] = field(default_factory=list)
    recoverable_aud: float = 0.0
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "merchant_id": self.merchant_id,
            "off": {**asdict(self.off), "win_rate_pct": self.off.win_rate_pct},
            "on": {**asdict(self.on), "win_rate_pct": self.on.win_rate_pct},
            "reasons": [asdict(r) for r in self.reasons],
            "recoverable_aud": self.recoverable_aud,
            "note": self.note,
        }


def _condition(
    extension: str,
    request: str,
    offers: list[Offer],
    policy: CustomerPolicy,
    keyring: KeyRing,
    *,
    repeats: int,
    allow_network: bool,
    merchant_id: str,
) -> ConditionResult:
    tally = rp.run_repeats(
        request, offers, policy, keyring, repeats=repeats, allow_network=allow_network
    )
    counts = tally.counts
    won = counts.get(merchant_id, 0)
    return ConditionResult(
        extension=extension,
        comparisons=tally.n_recorded,
        won=won,
        lost=tally.n_recorded - won,
        lost_to={k: v for k, v in counts.items() if k != merchant_id},
        headline=tally.headline(),
    )


def _valuation(
    offers: list[Offer], policy: CustomerPolicy, keyring: KeyRing, merchant_id: str
) -> Valuation | None:
    valuations = trv_rank(offers, policy, keyring)
    return next((v for v in valuations if v.offer.merchant_id == merchant_id), None)


def attribute(
    offers_on: list[Offer],
    offers_off: list[Offer],
    policy: CustomerPolicy,
    keyring: KeyRing,
    *,
    merchant_id: str = FOCUS_MERCHANT,
) -> tuple[list[LossReason], float]:
    """Name the benefits the agent could not see, priced by the same ledger.

    The comparison is between the two payloads that actually went out, so a
    benefit counts as "reached the agent" only if it survived capability
    negotiation — not if we merely intended to send it.
    """
    on = _valuation(offers_on, policy, keyring, merchant_id)
    if on is None:
        return [], 0.0

    off_offer = next((o for o in offers_off if o.merchant_id == merchant_id), None)
    delivered = {b.title for b in (off_offer.benefits if off_offer else [])}

    reasons: list[LossReason] = []
    for line in on.lines:
        if line.amount_aud >= 0:  # penalties are not value the merchant lost
            continue
        reasons.append(
            LossReason(
                title=line.label,
                value_aud=round(-line.amount_aud, 2),
                status=line.status,
                published=True,
                reached_agent=line.label in delivered,
            )
        )
    reasons.sort(key=lambda r: -r.value_aud)

    # Ceiling discipline: only signed, cost-reducing value the agent never saw.
    recoverable = round(
        sum(r.value_aud for r in reasons if r.status == "signed" and not r.reached_agent),
        2,
    )
    return reasons, recoverable


def run(
    request: str,
    offers_off: list[Offer],
    offers_on: list[Offer],
    policy: CustomerPolicy,
    keyring: KeyRing,
    *,
    repeats: int = rp.DEFAULT_REPEATS,
    allow_network: bool = False,
    merchant_id: str = FOCUS_MERCHANT,
) -> Scoreboard:
    off = _condition(
        "off", request, offers_off, policy, keyring,
        repeats=repeats, allow_network=allow_network, merchant_id=merchant_id,
    )
    on = _condition(
        "on", request, offers_on, policy, keyring,
        repeats=repeats, allow_network=allow_network, merchant_id=merchant_id,
    )
    reasons, recoverable = attribute(
        offers_on, offers_off, policy, keyring, merchant_id=merchant_id
    )

    total = off.comparisons + on.comparisons
    if not total:
        note = (
            "No comparison was recorded. Every run fell back to list-price "
            "ranking, which is reported and never counted."
        )
    elif off.lost and not on.lost:
        hidden = [r for r in reasons if r.status == "signed" and not r.reached_agent]
        note = (
            f"Lost {off.lost} of {off.comparisons} comparisons while invisible; "
            f"won {on.won} of {on.comparisons} once legible. "
            f"${recoverable:.2f} of signed value across {len(hidden)} benefits was "
            "on the merchant's own website and never reached the agent."
        )
    else:
        note = (
            f"{off.headline} with the extension off, {on.headline} with it on. "
            "Reported as it fell."
        )

    return Scoreboard(
        merchant_id=merchant_id,
        off=off,
        on=on,
        reasons=reasons,
        recoverable_aud=recoverable,
        note=note,
    )
