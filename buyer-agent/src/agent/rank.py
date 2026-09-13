"""The two load-bearing model calls: decoding the sentence, and deciding the order.

The agent decides. Nothing here computes an effective cost and nothing here
consults one -- the model is handed the *facts* a merchant attached to a
listing and judges what they are worth, which is the part of the problem that
does not reduce to arithmetic.

The offer payload deliberately withholds ``credited`` and ``effective_cost``
even though ``run_request`` has already computed them. Handing the model a
per-record dollar value would be handing it the answer and then reporting its
agreement as a decision. What it sees is the shelf price and the terms.

A claim that did not verify is passed through marked ``verified: false`` rather
than dropped, so the model can be seen declining to credit it.
"""

from __future__ import annotations

import json
from typing import Any

from bondlayer import ai
from bondlayer.agent.composition import _search_query
from bondlayer.agent.trace import AgentRun, Ranked
from bondlayer.interpreter.openai import decode
from bondlayer.types import ConstraintKind

from . import llm
from .ucp_client import _CATEGORIES

AGENT_SYSTEM_PROMPT = """You are a shopping agent acting for a customer. You compare \
offers from several merchants and pick the one that serves the customer best.

Some merchants attach additional structured terms to a listing beyond its price: \
warranty length, shipping terms, repair commitments. Each carries a cryptographic \
signature that has already been checked for you, and the data tells you whether it \
verified.

Most of these terms are facts, not prices. A 24-month warranty against a statutory \
12 is a real difference, but it has no exchange rate against a lower shelf price -- \
do not invent one. Judge what the terms are worth to this customer as a person would: \
how long they will keep the thing, what failure would cost them, whether a waived \
delivery fee matters at this price. A term that is merely the legal minimum is not an \
advantage.

A claim that did not verify is not evidence. It must not move your ranking, however \
large the number attached to it.

Be neutral and concrete. Never invent a benefit that is not in the data you were \
given, and be willing to prefer the cheaper offer when the extra terms do not earn \
their premium."""

def parse_intent(utterance: str) -> dict:
    """One shared decode supplies both search parameters and hard-clause checks."""
    constraints, meta = decode(utterance)
    _, plan = _search_query(constraints)
    price = plan.get("max_price")
    return {
        "summary": utterance, "category": plan.get("category"),
        "max_price_aud": float(price) if price is not None else None,
        "must_have": [c.text for c in constraints if c.kind != ConstraintKind.HARD],
        "constraints": [{"text": c.text, "kind": c.kind.value} for c in constraints],
        "ai": meta,
    }


def _known_category(value: object) -> str | None:
    """The model's category, only if the catalogue actually has one by that name.

    A category the search route does not recognise is worse than none at all:
    it filters every listing out and the run comes back empty. The model was
    given the vocabulary, but "laptops" for "laptop" is one plural away from an
    empty demo, so the answer is checked rather than trusted. Anything that does
    not match is dropped, and the interpreter's own plan backfills it.
    """
    if not isinstance(value, str):
        return None
    candidate = value.strip().lower()
    if candidate in _CATEGORIES:
        return candidate
    singular = candidate[:-1] if candidate.endswith("s") else candidate + "s"
    return singular if singular in _CATEGORIES else None


def plan_from_intent(intent: dict) -> dict:
    """The model's decode, spelled as the typed search plan the fetcher reads.

    Shape matches what ``composition.run_request`` hands a ``Fetcher`` so the
    existing ``_params_from_plan`` reads it unchanged.
    """
    price = intent.get("max_price_aud")
    return {
        "category": _known_category(intent.get("category")),
        "max_price": price if isinstance(price, (int, float)) else None,
        # ``must_have`` deliberately does not become ``terms``. The search route
        # spells ``terms`` as ``q`` and filters titles by substring, so a phrase
        # like "easy return policies" matches no title and empties the run. It
        # would also put a SERVICE clause on the wire, and those are withheld
        # agent-side precisely so no merchant can price against them. The
        # product noun comes from the interpreter's own plan; what the shopper
        # wants *honoured* is for the resolver and the ranking to weigh.
    }


def _offer_payload(r: Ranked) -> dict:
    """One offer as the model sees it: the price, and the terms. No arithmetic."""
    terms = []
    for c in r.citations:
        if c.get("record_id") is None:
            continue
        terms.append({
            "record_id": c["record_id"],
            "term": c.get("benefit_type"),
            "says": c.get("why"),
            "verified": bool(c.get("cited")),
        })
    return {
        "sku_id": r.sku_id,
        "merchant": r.merchant,
        "title": r.title,
        "shelf_price_aud": float(r.shelf_price),
        "attached_terms": terms,
    }


def rank_offers(utterance: str, run: AgentRun) -> dict:
    """Rank every offer. One live call. Returns the model's answer verbatim."""
    payload = [_offer_payload(r) for r in run.ranked]
    ranking = llm.complete_json(
        "rank",
        AGENT_SYSTEM_PROMPT,
        f'The customer asked: "{utterance}"\n\n'
        f"Offers:\n{json.dumps(payload, indent=2)}\n\n"
        "Rank every offer from best to worst for this customer. Decide for yourself "
        "what the attached terms are worth to them -- most are facts, not prices, and "
        "there is no exchange rate between a longer warranty and a lower price. Say "
        "which terms moved your decision and which you discounted.\n\n"
        "Reply as JSON:\n"
        '{"ranking": [{"rank": 1, "sku_id": "...", "merchant": "...", '
        '"decisive_terms": ["the verified terms that actually moved this offer up or '
        'down, or [] if price alone decided it"], '
        '"reasoning": "one or two sentences"}], '
        '"recommendation": "one short paragraph to the customer"}',
    )
    if not isinstance(ranking, dict) or not isinstance(ranking.get("ranking"), list):
        raise ai.AIError("OpenAI did not return a usable ranking. Please retry.")
    return ranking


def apply_ranking(run: AgentRun, ranking: dict) -> dict[tuple[str, str], Any]:
    """Reorder ``run.ranked`` into the model's order, in place.

    ``AgentRun`` is frozen but ``ranked`` is a list, so this rebinds its
    contents without touching ``bondlayer``. Everything downstream that reads
    ``run.winner`` -- the close-loop checkout above all -- then follows the
    model's pick rather than the arithmetic's.

    An offer the model omitted is kept, appended in its original relative
    order. Dropping it would let a model silently disappear a listing a
    merchant did return.
    """
    by_offer = {(r.merchant, r.sku_id): r for r in run.ranked}
    notes: dict[tuple[str, str], Any] = {}
    ordered: list[Ranked] = []
    seen: set[tuple[str, str]] = set()

    for row in ranking.get("ranking") or []:
        if not isinstance(row, dict):
            continue
        merchant, sku = row.get("merchant"), row.get("sku_id")
        if not isinstance(merchant, str) or not isinstance(sku, str):
            continue
        key = (merchant, sku)
        offer = by_offer.get(key)
        if offer is None or key in seen:
            continue
        seen.add(key)
        ordered.append(offer)
        terms = row.get("decisive_terms")
        notes[key] = {
            "decisive_terms": [str(t) for t in terms] if isinstance(terms, list) else [],
            "reasoning": str(row.get("reasoning") or ""),
        }

    if run.ranked and not ordered:
        raise ai.AIError("OpenAI did not select a known offer. Please retry.")
    ordered.extend(r for r in run.ranked if (r.merchant, r.sku_id) not in seen)
    run.ranked[:] = ordered
    return notes
