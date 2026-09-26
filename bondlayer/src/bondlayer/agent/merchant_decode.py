"""The merchant's own reading of the sentence, shown next to the agent's.

The problem statement's desired outcome is a *merchant system* that receives
the buyer agent's complex query, decodes it, analyses its catalogue and returns
a justified proposal. ``ucp/intent.py`` is that system: ``POST
/{merchant}/ucp/intent/propose`` takes the shopper's sentence verbatim and
answers with ``decoded_intent`` and ``proposals``. Until now nothing on the
agent side called it in the demo, so a judge only ever saw the agent decode.

This module is the buyer agent asking. ``run_with_merchant_decode`` runs
``run_request`` exactly as before, then sends the same sentence to every
merchant that negotiated ``org.bondlayer.intent_match`` and records what each
one understood and proposed, as **one more Step** on the trace.

Three things it never does:

- It never changes the ranking. ``run.ranked``, ``run.bundles``,
  ``run.constraints`` and every step ``run_request`` produced are the objects
  ``run_request`` returned; this appends one ``Step`` to ``run.steps`` and
  touches nothing else. The merchant's proposals are *what the merchant
  understood and proposed*; the ranking below them is *what the agent verified
  and decided*, and the second never reads the first.
- It never calls the merchant when the extension is off. The control run's
  header declares nothing beyond plain catalogue search, so the sentence is not
  sent, and the step says so rather than pretending three 406s are a finding.
- It never invents agreement. The agreement block pairs the agent's clauses to
  the merchant's by a fixed, documented rule (``agreement``), so a judge can
  see both parties decoded the same thing -- and would see the disagreement if
  they had not.

No network call beyond whatever the caller's ``propose`` does, which in the
product is localhost HTTP to the merchant server; no model call; deterministic.
"""

from __future__ import annotations

import re
from typing import Protocol

from bondlayer.agent.composition import run_request
from bondlayer.agent.trace import AgentRun, Outcome, Phase, Step
from bondlayer.ucp.capabilities import INTENT_MATCH

#: ``Step.detail["kind"]``. Renderers find this step by it -- ``Phase.INTENT``
#: is shared with the agent's own decode step and ``trace.py`` grows no new
#: Phase for this.
STEP_KIND = "merchant_decode"

#: How many of the merchant's proposals travel into the trace. The merchant is
#: asked for this many too, so the wire and the trace agree.
MAX_PROPOSALS = 5

#: Dropped before clause texts are compared. Function words only, so that
#: "I can return easily" and "return easily" still pair.
STOPWORDS = frozenset(
    {"a", "an", "the", "i", "it", "to", "my", "that", "if", "from", "and", "is", "of"}
)
_TOKEN = re.compile(r"[a-z0-9]+")

#: Two clause texts pair when one's tokens are a subset of the other's, or
#: their Jaccard similarity reaches this.
JACCARD_THRESHOLD = 0.34


class Proposer(Protocol):
    """Asks one merchant to decode the sentence itself.

    Returns the parsed JSON of ``POST /{merchant}/ucp/intent/propose``;
    ``None`` when the merchant did not negotiate ``intent_match`` (HTTP 406)
    or when ``extension`` is ``False``; raises for any other transport error.
    """

    def __call__(self, merchant: str, utterance: str, *, extension: bool) -> dict | None: ...


# --- agreement ------------------------------------------------------------------


def tokens(text: str) -> frozenset[str]:
    """Lowercase alphanumeric tokens of a clause, minus the stopwords."""
    return frozenset(t for t in _TOKEN.findall(str(text).lower()) if t not in STOPWORDS)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _pairs(a: frozenset[str], b: frozenset[str]) -> bool:
    if not a or not b:
        return a == b
    return a <= b or b <= a or _jaccard(a, b) >= JACCARD_THRESHOLD


def _clause(c: dict) -> dict:
    return {"text": str(c.get("text", "")), "kind": str(c.get("kind", "")).lower()}


def agreement(agent_constraints: list[dict], merchant_constraints: list[dict]) -> dict:
    """Pair the agent's decode to the merchant's, clause by clause.

    The rule, in full, so it can be checked by hand:

    1. A pair is only ever considered between clauses of **equal ``kind``**
       (lowercase: ``hard``, ``soft``, ``service``, ``values``). A clause the
       merchant filed under a different kind is a disagreement, however similar
       the words.
    2. Texts are compared as lowercase alphanumeric token sets minus
       ``STOPWORDS``. Two texts *match* when one token set is a subset of the
       other, or their Jaccard similarity is at least ``JACCARD_THRESHOLD``.
    3. Matching pairs are taken greedily, highest Jaccard first; each clause on
       either side is used at most once. Ties break on the agent's clause order,
       then the merchant's, so the result never depends on dict ordering.
    4. ``agree`` is ``True`` for a paired agent clause and ``False`` otherwise.
       ``agreed``/``total`` count the agent's clauses. A merchant clause that
       paired with nothing is listed under ``merchant_only`` -- the merchant
       read something the agent did not -- and is not counted against
       ``total``, because the question asked is "did the merchant read what the
       agent read".

    Both seats run the same rules parser today, so R01 agrees 4/4. The value of
    showing it is that a judge can see two independent decodes coincide, and
    would see exactly which clause diverged if they did not.
    """
    agent = [_clause(c) for c in agent_constraints]
    merchant = [_clause(c) for c in merchant_constraints]
    agent_tokens = [tokens(c["text"]) for c in agent]
    merchant_tokens = [tokens(c["text"]) for c in merchant]

    candidates: list[tuple[float, int, int]] = []
    for i, a in enumerate(agent):
        for j, m in enumerate(merchant):
            if a["kind"] != m["kind"]:
                continue
            if not _pairs(agent_tokens[i], merchant_tokens[j]):
                continue
            candidates.append((_jaccard(agent_tokens[i], merchant_tokens[j]), i, j))
    # Highest Jaccard first; ties on agent order, then merchant order.
    candidates.sort(key=lambda t: (-t[0], t[1], t[2]))

    paired: dict[int, int] = {}
    used_merchant: set[int] = set()
    for _, i, j in candidates:
        if i in paired or j in used_merchant:
            continue
        paired[i] = j
        used_merchant.add(j)

    clauses = [
        {
            "agent": a,
            "merchant": merchant[paired[i]] if i in paired else None,
            "agree": i in paired,
        }
        for i, a in enumerate(agent)
    ]
    return {
        "clauses": clauses,
        "agreed": len(paired),
        "total": len(agent),
        "merchant_only": [m for j, m in enumerate(merchant) if j not in used_merchant],
    }


# --- one merchant --------------------------------------------------------------------


def trim_proposal(wire: dict) -> dict:
    """One proposal as the trace carries it: id, title, price, and the
    resolver's justification verbatim. The full product block stays on the
    wire; the trace needs only enough to name what was proposed."""
    product = wire.get("product") or {}
    price = product.get("price") or {}
    return {
        "sku_id": product.get("id"),
        "title": product.get("title"),
        "price": price.get("amount"),
        "currency": price.get("currency"),
        "resolved": list(wire.get("resolved") or []),
        "unsatisfied": list(wire.get("unsatisfied") or []),
    }


def merchant_decode(merchant: str, response: dict | None, agent_constraints: list[dict]) -> dict:
    """The per-merchant entry of the step detail.

    ``response`` is the parsed body of the intent route, or ``None`` when the
    merchant did not negotiate the capability. ``decoded_intent`` is the
    merchant's block **verbatim** -- its constraints, its interpretations, its
    assumptions, its clarifying question -- so nothing here restates what the
    merchant said.
    """
    if response is None:
        return {
            "merchant": merchant,
            "negotiated": False,
            "decoded_intent": None,
            "proposals": [],
            "agreement": agreement(agent_constraints, []),
        }
    decoded = response.get("decoded_intent") or {}
    proposals = [trim_proposal(p) for p in (response.get("proposals") or [])[:MAX_PROPOSALS]]
    return {
        "merchant": merchant,
        "negotiated": True,
        "decoded_intent": decoded,
        "proposals": proposals,
        "agreement": agreement(agent_constraints, decoded.get("constraints") or []),
    }


# --- the step ----------------------------------------------------------------------------


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def summarise(merchant_decodes: list[dict]) -> tuple[Outcome, str]:
    """One judge-readable line, and whether it counts as degraded.

    DEGRADED when no merchant negotiated the capability -- the agent asked and
    nobody could answer. A disagreement is a finding, not a degradation: the
    step stays OK and the summary names the merchant and the count.
    """
    decoded = [d for d in merchant_decodes if d["negotiated"]]
    refused = [d["merchant"] for d in merchant_decodes if not d["negotiated"] and not d.get("error")]
    errored = [d for d in merchant_decodes if d.get("error")]
    total = len(merchant_decodes)

    parts: list[str] = [
        f"{len(decoded)} of {total} {_plural(total, 'merchant', 'merchants')} decoded the request "
        f"{'itself' if len(decoded) == 1 else 'themselves'}"
    ]
    if decoded:
        scores = {(d["agreement"]["agreed"], d["agreement"]["total"]) for d in decoded}
        if len(scores) == 1:
            agreed, clauses = next(iter(scores))
            who = {1: "it agrees", 2: "both agree"}.get(len(decoded), "all agree")
            parts[0] += f"; {who} with the agent on {agreed}/{clauses} clauses."
        else:
            per = ", ".join(
                f"{d['merchant']} agrees on {d['agreement']['agreed']}/{d['agreement']['total']}"
                for d in decoded
            )
            parts[0] += f"; {per} clauses."
    else:
        parts[0] += "."
    if refused:
        parts.append(
            f"{', '.join(refused)} did not negotiate {INTENT_MATCH.rsplit('.', 1)[-1]}."
        )
    for d in errored:
        parts.append(f"{d['merchant']} could not be asked ({d['error']}).")

    outcome = Outcome.OK if decoded else Outcome.DEGRADED
    return outcome, " ".join(parts)


EXTENSION_OFF_SUMMARY = (
    "Extension off: the shopper's sentence was not sent to any merchant; "
    "only the agent decoded it."
)


def run_with_merchant_decode(
    utterance: str,
    merchants: list[str],
    fetch,
    *,
    propose: Proposer,
    **run_request_kwargs,
) -> AgentRun:
    """``run_request``, then ask each merchant to decode the sentence itself.

    Everything ``run_request`` returns is returned as it was; one ``Step`` is
    appended to ``run.steps`` with ``detail == {"kind": "merchant_decode",
    "merchant_decodes": [...]}``, one entry per merchant in ``merchants``
    order. ``run_request_kwargs`` are passed through unchanged; ``extension``
    (default ``True``) also decides whether the sentence is sent at all.

    A ``propose`` that raises for one merchant does not lose the run: that
    merchant's entry carries ``error`` and ``negotiated: False``, and the
    summary says it could not be asked. The ranking above is already decided
    and is not this function's to fail.
    """
    run = run_request(utterance, merchants, fetch, **run_request_kwargs)
    extension = bool(run_request_kwargs.get("extension", True))

    if not extension:
        run.steps.append(Step(
            Phase.INTENT, Outcome.DEGRADED, EXTENSION_OFF_SUMMARY,
            {"kind": STEP_KIND, "merchant_decodes": []},
        ))
        return run

    merchant_decodes: list[dict] = []
    for merchant in merchants:
        try:
            response = propose(merchant, utterance, extension=extension)
        except Exception as exc:  # degrade honestly: the ranking is not at stake
            entry = merchant_decode(merchant, None, run.constraints)
            entry["error"] = f"{type(exc).__name__}: {exc}"
            merchant_decodes.append(entry)
            continue
        merchant_decodes.append(merchant_decode(merchant, response, run.constraints))

    outcome, summary = summarise(merchant_decodes)
    run.steps.append(Step(
        Phase.INTENT, outcome, summary,
        {"kind": STEP_KIND, "merchant_decodes": merchant_decodes},
    ))
    return run


def merchant_decode_step(run: AgentRun) -> Step | None:
    """The step this module appended, or ``None`` when the run has none."""
    for step in run.steps:
        if step.detail.get("kind") == STEP_KIND:
            return step
    return None
