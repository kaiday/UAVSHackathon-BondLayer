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

from bondlayer.types import Bundle, Constraint, ResolvedConstraint


class Phase(str, Enum):
    INTENT = "intent"
    # Which clause each offer answers, and on what: a catalogue attribute or a
    # verified record, cited by id. INTENT decodes what the shopper said;
    # RESOLVE says what the shelf can answer, one clause at a time. This is the
    # justification the problem statement asks for -- "a logical justification
    # of WHY these products match, not a SKU list".
    RESOLVE = "resolve"
    DISCOVERY = "discovery"
    NEGOTIATION = "negotiation"
    VERIFICATION = "verification"
    VALUATION = "valuation"
    RANKING = "ranking"
    # Composition, after the ranking: which of the ranked offers belong
    # together as a set. Never a verification claim, so never `is_evidence`.
    BUNDLE = "bundle"


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
    #: One entry per clause the shopper said, as the interpreter's resolver
    #: answered it *for this listing*: the catalogue attribute or the verified
    #: record that answers it, and a one-sentence note saying why. Empty when no
    #: interpreter was wired -- additive, so every existing caller is unchanged.
    #:
    #: A record id appears here only if the caller's own verifier passed it, so
    #: an unsigned record can be seen on the wire and can never be cited.
    resolved: list[ResolvedConstraint] = field(default_factory=list)
    #: The clauses this listing answers with nothing at all. Kept honestly
    #: rather than dropped: it is the half of the justification that says what
    #: the shelf could not do.
    unsatisfied: list[Constraint] = field(default_factory=list)


@dataclass(frozen=True)
class AgentRun:
    """One shopper request, end to end, with its reasoning attached."""

    utterance: str
    extension_enabled: bool
    steps: list[Step]
    ranked: list[Ranked]
    constraints: list[dict] = field(default_factory=list)
    unsatisfied: list[dict] = field(default_factory=list)
    #: Sets composed from the ranked offers, best first. Empty when no bundler
    #: was wired -- additive, so every existing caller keeps working unchanged.
    bundles: list[Bundle] = field(default_factory=list)

    @property
    def winner(self) -> Ranked | None:
        return self.ranked[0] if self.ranked else None

    @property
    def degraded(self) -> list[Step]:
        return [s for s in self.steps if s.outcome in (Outcome.DEGRADED, Outcome.ABSENT)]
