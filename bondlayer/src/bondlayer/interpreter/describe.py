"""Explain a decode in JSON, so the agent can see how the merchant read it.

The merchant-side intent route (``ucp/intent.py``) hands the shopper's sentence
to ``parser.parse`` and the resolver. This module renders what the resolver is
*about to apply* -- not a second reading of the sentence. It wraps the
resolver's own interpreters, ``interpret_hard``, ``interpret_soft`` and
``interpret_record_need``, and turns their dataclasses into plain dicts. The
explanation and the behaviour are the same objects, so they cannot drift.

Three things come out of a decode, all deterministic and all derived from the
constraints alone:

- ``describe(constraint)`` -- one clause, its kind, and a JSON-safe
  ``interpretation`` (``{"category": "laptop", "max_price_aud": "1500"}``).
- ``assumptions(constraints)`` -- one plain sentence per reading the merchant
  made that the shopper did not literally say. Only sentences that are true
  for *this* utterance are emitted.
- ``clarifying_question(constraints)`` -- one question, or ``None``. Set only
  when nothing in the request names a product or a category, which is the
  case where confidence is genuinely low. Never a hard failure: the proposals
  still come back, over the whole shelf, and the question says so.

Decimals are rendered as strings, matching ``price.amount`` on the wire.
"""

from __future__ import annotations

import re
from decimal import Decimal

from bondlayer.interpreter.resolver import (
    HardSpec,
    RecordNeed,
    SoftSignal,
    interpret_hard,
    interpret_record_need,
    interpret_soft,
)
from bondlayer.types import Constraint, ConstraintKind

#: The two kinds no catalogue column can answer. Counted for the agent.
EVIDENCE_KINDS = (ConstraintKind.SERVICE, ConstraintKind.VALUES)

#: Catalogue attribute names a SOFT signal's phrase can mention. The phrase is
#: the resolver's human-readable ``inferred`` string; these are lifted out of it
#: so the agent gets typed names, not prose.
_ATTRIBUTE_NAMES = ("shelf_price", "weight_kg", "ram_gb", "storage_gb", "screen_in", "gpu", "cpu", "category")

_HARD_CEILING_WORD = re.compile(r"\b(under|below|less\s+than|no\s+more\s+than|up\s+to)\b", re.IGNORECASE)


def _jsonable(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    return value


def _fmt_money(value: Decimal) -> str:
    return f"${value:,.2f}"


# --- one clause ----------------------------------------------------------------


def _hard_interpretation(specs: list[HardSpec]) -> dict:
    out: dict = {}
    for spec in specs:
        if spec.kind == "price":
            out["max_price_aud"] = str(spec.value)
        elif spec.kind == "weight":
            out["max_weight_kg"] = spec.value
        elif spec.kind == "category":
            out["category"] = spec.value
            if spec.narrow:
                out["implies_attribute"] = spec.narrow
        elif spec.kind == "ram":
            out["ram_gb"] = spec.value
        elif spec.kind == "storage":
            out["storage_gb"] = spec.value
        elif spec.kind == "screen":
            out["screen_in"] = spec.value
        elif spec.kind == "gpu":
            out["gpu"] = spec.value
        elif spec.kind == "cpu":
            out["cpu_family"] = spec.value
        elif spec.kind == "product":
            out["product_tokens"] = spec.value
        else:
            out["unrecognised"] = True
    return {k: _jsonable(v) for k, v in out.items()}


def _soft_interpretation(signal: SoftSignal | None) -> dict:
    if signal is None:
        return {"unrecognised": True}
    mentioned = [name for name in _ATTRIBUTE_NAMES if name in signal.inferred]
    return {"signal": signal.inferred, "attributes": mentioned}


def _record_interpretation(need: RecordNeed | None) -> dict:
    if need is None:
        return {"unrecognised": True}
    out: dict = {"benefit_type": need.benefit_type.value}
    if need.predicate_text:
        out["fact_requires"] = need.predicate_text
    return out


def interpretation(constraint: Constraint) -> dict:
    """What the resolver will do with this clause, as a JSON-safe dict."""
    if constraint.kind is ConstraintKind.HARD:
        return _hard_interpretation(interpret_hard(constraint.text))
    if constraint.kind is ConstraintKind.SOFT:
        return _soft_interpretation(interpret_soft(constraint.text))
    return _record_interpretation(interpret_record_need(constraint.text))


def describe(constraint: Constraint) -> dict:
    """One entry of ``decoded_intent.constraints``."""
    return {
        "text": constraint.text,
        "kind": constraint.kind.value,
        "interpretation": interpretation(constraint),
    }


# --- the whole decode ----------------------------------------------------------


def _hard_specs(constraints: list[Constraint]) -> list[tuple[Constraint, HardSpec]]:
    return [
        (c, spec)
        for c in constraints
        if c.kind is ConstraintKind.HARD
        for spec in interpret_hard(c.text)
    ]


def names_a_product(constraints: list[Constraint]) -> bool:
    """True when some HARD clause names a category or a product.

    This is the confidence test: a request that says what kind of thing it is
    for can be filtered; one that does not is answered over the whole shelf
    and earns a clarifying question.
    """
    return any(spec.kind in ("category", "product") for _, spec in _hard_specs(constraints))


def unanswerable_from_catalogue(constraints: list[Constraint]) -> int:
    """How many clauses no catalogue column can answer (SERVICE + VALUES)."""
    return sum(1 for c in constraints if c.kind in EVIDENCE_KINDS)


def assumptions(constraints: list[Constraint]) -> list[str]:
    """Plain sentences, one per reading the merchant made. Only true ones."""
    out: list[str] = []
    specs = _hard_specs(constraints)

    for c, spec in specs:
        if spec.kind == "price":
            m = _HARD_CEILING_WORD.search(c.text)
            word = re.sub(r"\s+", " ", m.group(1).lower()) if m else "under"
            out.append(
                f"Budget of {_fmt_money(spec.value)} read as a hard ceiling because the "
                f"shopper said '{word}', not 'around'."
            )
        elif spec.kind == "weight":
            out.append(
                f"Weight bound of {spec.value:g}kg applied to the typed weight_kg attribute; "
                "a listing that publishes no weight is excluded, not guessed."
            )
        elif spec.kind == "category":
            out.append(
                f"Category read as '{spec.value}' from '{c.text}'; the catalogue has no finer "
                "product type, so every listing in that category passes the category check."
            )
        elif spec.kind == "product":
            out.append(
                f"'{c.text}' read as a product name and matched over normalised title, brand "
                "and model tokens, not by substring."
            )
        elif spec.kind == "unknown":
            out.append(
                f"'{c.text}' could not be read as a catalogue filter and was not applied; "
                "it is reported as unsatisfied rather than used to exclude anything."
            )

    if not any(spec.kind == "category" for _, spec in specs):
        out.append("No product category was stated; nothing was excluded on category.")

    for c in constraints:
        if c.kind is ConstraintKind.SOFT:
            signal = interpret_soft(c.text)
            if signal is None:
                out.append(
                    f"'{c.text}' has no ranking heuristic; it stays in the justification as "
                    "unanswered and excludes nothing."
                )
            elif signal.inferred.startswith("shelf_price closest to"):
                out.append(
                    f"'{c.text}' read as a price preference, not a ceiling; listings are ordered "
                    "by distance from it and none is excluded on price."
                )
            else:
                out.append(
                    f"'{c.text}' ranks listings by {signal.inferred}; it excludes nothing."
                )

    for c in constraints:
        if c.kind in EVIDENCE_KINDS:
            need = interpret_record_need(c.text)
            if need is None:
                out.append(
                    f"'{c.text}' has no catalogue attribute and could not be mapped to a "
                    "benefit type; it is reported as unanswered."
                )
            else:
                out.append(
                    f"'{c.text}' has no catalogue attribute and can only be answered from a "
                    f"published benefit record of type '{need.benefit_type.value}'."
                )
    return out


def clarifying_question(constraints: list[Constraint]) -> str | None:
    """One question when confidence is low; ``None`` otherwise.

    Never a hard failure on ambiguity: the route still returns proposals over
    the whole shelf, and this sentence tells the agent why the list is wide.
    """
    if names_a_product(constraints):
        return None
    return (
        "Which kind of product is this for? Nothing in the request names one, "
        "so nothing was excluded on category."
    )
