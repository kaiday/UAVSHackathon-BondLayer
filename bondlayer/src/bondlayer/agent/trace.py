"""What the agent did, in the order it did it.

The console log is a rendering of this and nothing else. If a line appears on
screen that is not a ``Step`` here, it was invented in the UI, which is exactly
the failure the Problem Setter's note warns about -- logic visible, not logic
implied.

Steps carry a ``detail`` dict rather than a formatted string so the same trace
can be rendered as a log, asserted in a test, or dropped into the deck.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


class Phase(str, Enum):
    INTENT = "intent"
    DISCOVERY = "discovery"
    NEGOTIATION = "negotiation"
    VERIFICATION = "verification"
    VALUATION = "valuation"
    RANKING = "ranking"


class Outcome(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"  # worked, but with less than the full picture
    REFUSED = "refused"  # a legitimate protocol answer, e.g. 406
    ABSENT = "absent"  # a component that is not wired yet


@dataclass(frozen=True)
class Step:
    phase: Phase
    outcome: Outcome
    summary: str  # one line, merchant- or judge-readable
    detail: dict = field(default_factory=dict)

    @property
    def is_evidence(self) -> bool:
        """A step a judge could be asked to justify."""
        return self.phase in (Phase.VERIFICATION, Phase.VALUATION, Phase.RANKING)


@dataclass(frozen=True)
class Ranked:
    merchant: str
    sku_id: str
    title: str
    shelf_price: Decimal
    credited: Decimal
    effective_cost: Decimal
    records_seen: int
    records_verified: int
    records_credited: int
    citations: list[dict] = field(default_factory=list)
    withheld_note: str | None = None


@dataclass(frozen=True)
class AgentRun:
    """One shopper request, end to end, with its reasoning attached."""

    utterance: str
    extension_enabled: bool
    steps: list[Step]
    ranked: list[Ranked]
    constraints: list[dict] = field(default_factory=list)
    unsatisfied: list[dict] = field(default_factory=list)

    @property
    def winner(self) -> Ranked | None:
        return self.ranked[0] if self.ranked else None

    @property
    def degraded(self) -> list[Step]:
        return [s for s in self.steps if s.outcome in (Outcome.DEGRADED, Outcome.ABSENT)]
