"""Live intent decoding into the existing deterministic interpreter contract."""

from bondlayer import ai
from bondlayer.types import Constraint, ConstraintKind


class Clause(ai.AIModel):
    source_span: str
    normalized_text: str
    kind: ConstraintKind


class Intent(ai.AIModel):
    clauses: list[Clause]


def decode(utterance: str) -> tuple[list[Constraint], dict]:
    if ai.mode() == "rules":
        from bondlayer.interpreter.parser import parse
        return parse(utterance), {"provider": "rules", "mode": "explicit_offline"}
    result, meta = ai.structured(
        "intent",
        "Decode a shopping request into hard requirements, soft preferences, service requirements "
        "and values preferences. Quote a verbatim source_span for every clause. Normalize synonyms "
        "and units in normalized_text so a deterministic electronics resolver can interpret them "
        "(e.g. notebook computer -> laptop, below fifteen hundred -> under $1500, "
        "within a budget of 3000 -> under $3000, "
        "sixteen gigs -> at least 16GB RAM, 24 month warranty -> warranty at least 24 months). "
        "Separate category and budget clauses. Ordering words such as cheapest, best value or "
        "beginner-friendly are soft preferences, never hard requirements.Preserve negation and all explicit requirements. "
        "Never add a budget, product category or specification that the shopper did not request. "
        "Keep service and values requirements even when a catalogue cannot answer them. "
        "Return at most 20 clauses; use an empty list if there is no shopping intent.",
        {"utterance": utterance}, Intent,
    )
    if len(result.clauses) > 20 or any(
        not c.source_span.strip() or c.source_span not in utterance or not c.normalized_text.strip()
        for c in result.clauses
    ):
        raise ai.AIError("OpenAI's intent decode could not be tied to the original request. Please retry.")
    meta["clauses"] = [c.model_dump(mode="json") for c in result.clauses]
    return [Constraint(c.normalized_text, c.kind) for c in result.clauses], meta
