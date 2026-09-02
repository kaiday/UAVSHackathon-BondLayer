"""n = 5 per condition, with the payload order shuffled (demo-flow-v2 §3b).

Every fixture in this demo was a single temperature-0 completion, which the
README already names as the cheapest remaining experiment and the one most
likely to embarrass us on stage. This runs the ranking call five times per
condition and tallies the votes.

Two design points worth defending:

**The variation is the offer order, not a nonce.** Presenting the merchants in
a different permutation tests position bias -- the failure mode most likely to
be raised by a judge who has read anything about LLM evaluation -- and it
changes the prompt, so each repeat lands on its own fixture key without
touching `llm._key`.

**A miss is reported, never counted.** `run_llm_agent` falls back to list-price
ranking when no model answers, and that fallback would otherwise be tallied as
a model vote for Peak. A repeat with no fixture and no transport is recorded as
`not recorded` and excluded from the denominator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import permutations

from .. import llm
from ..schema import Offer
from ..signing import KeyRing
from .policy import CustomerPolicy
from .shopping_agent import run_llm_agent

#: Fixed and ordered, so the run is reproducible and the fixture set is finite.
#: Five of the six permutations of three merchants -- five is enough to show a
#: split and cheap enough to record by hand.
DEFAULT_REPEATS = 5


def orderings(n_offers: int, repeats: int = DEFAULT_REPEATS) -> list[tuple[int, ...]]:
    """Stable index permutations, longest-distance-first from the natural order."""
    perms = list(permutations(range(n_offers)))
    return perms[:repeats] if len(perms) >= repeats else (
        [perms[i % len(perms)] for i in range(repeats)]
    )


@dataclass
class RepeatVote:
    ordering: tuple[int, ...]
    winner: str | None
    recorded: bool
    reason: str
    provenance: str


@dataclass
class RepeatTally:
    votes: list[RepeatVote] = field(default_factory=list)

    @property
    def recorded_votes(self) -> list[RepeatVote]:
        return [v for v in self.votes if v.recorded]

    @property
    def n_recorded(self) -> int:
        return len(self.recorded_votes)

    @property
    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for v in self.recorded_votes:
            if v.winner:
                out[v.winner] = out.get(v.winner, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    @property
    def majority(self) -> str | None:
        counts = self.counts
        return next(iter(counts), None) if counts else None

    @property
    def unanimous(self) -> bool:
        return len(self.counts) == 1 and self.n_recorded > 0

    def headline(self) -> str:
        """The string that goes on the screen. A split vote is never rounded."""
        if not self.n_recorded:
            return "0 runs recorded"
        top = self.majority
        return f"{self.counts[top]}/{self.n_recorded} {top}"

    def as_dict(self) -> dict:
        return {
            "headline": self.headline(),
            "n_recorded": self.n_recorded,
            "n_attempted": len(self.votes),
            "counts": self.counts,
            "unanimous": self.unanimous,
            "majority": self.majority,
            "votes": [
                {
                    "ordering": list(v.ordering),
                    "winner": v.winner,
                    "recorded": v.recorded,
                    "reason": v.reason,
                    "provenance": v.provenance,
                }
                for v in self.votes
            ],
        }


def run_repeats(
    request: str,
    offers: list[Offer],
    policy: CustomerPolicy,
    keyring: KeyRing,
    *,
    repeats: int = DEFAULT_REPEATS,
    allow_network: bool = False,
) -> RepeatTally:
    """Rank `repeats` times, reordering the offers each time, and tally."""
    tally = RepeatTally()
    for order in orderings(len(offers), repeats):
        shuffled = [offers[i] for i in order]
        before = len(llm.TRANSCRIPT)
        run = run_llm_agent(
            request, shuffled, policy, keyring, allow_network=allow_network
        )
        calls = llm.TRANSCRIPT[before:]
        fell_back = any(c.source == "fallback" for c in calls)
        provenance = calls[-1].provenance if calls else "no call"
        tally.votes.append(
            RepeatVote(
                ordering=order,
                winner=None if fell_back else run.winner_merchant_id,
                recorded=not fell_back,
                reason="" if fell_back else run.explanation,
                provenance="not recorded" if fell_back else provenance,
            )
        )
    return tally
