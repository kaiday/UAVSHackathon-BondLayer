"""The agent-side composition root.

Three correct components can still never meet. This is where they meet: the
interpreter (Hieu), signature verification and valuation (Bach), and the served
catalogue and benefit extension (Nguyen). Nothing here implements any of them.

Two rules govern everything below.

**Fail closed.** A component that is not wired yet is ABSENT, and absent never
means "assume it passed". An unverifiable record is worth zero, an unwired
verifier means *every* record is worth zero, and the trace says so out loud. A
demo that silently credits unverified value is the exact failure the whole
proposal argues against.

**Degrade honestly.** Every component is optional and the run still completes
without it, at lower fidelity, with a Step recording what was missing. Today
records[] is empty everywhere and no verifier exists; the run still produces a
ranking on shelf price and a trace that explains why nothing was credited.
That is a truthful demo of an incomplete system, which beats a fabricated demo
of a complete one.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable, Protocol

from bondlayer.agent.trace import AgentRun, Outcome, Phase, Ranked, Step

#: The extension's reverse-domain name, as negotiated on the wire.
BENEFIT_EXT = "org.bondlayer.benefit_value"

#: What the shopper thinks each benefit is worth. Lives agent-side and is never
#: sent to a merchant, so no merchant can price against it (proposal §5.3).
DEFAULT_POLICY: dict[str, Decimal] = {
    "free_returns": Decimal("72.00"),
    "warranty": Decimal("96.00"),
    "member_price": Decimal("9999"),  # face value, never capped by the shopper
    "points_earn": Decimal("9999"),
    "trade_in_credit": Decimal("9999"),
    "delivery": Decimal("9999"),
}


class Fetcher(Protocol):
    """Returns a parsed UCP search response for one merchant."""

    def __call__(self, merchant: str, query: str, *, extension: bool) -> dict: ...


def _decimal(v: Any) -> Decimal:
    # price.amount is a STRING, quantized to 2dp. Never re-round it.
    return Decimal(str(v))


def run_request(
    utterance: str,
    merchants: list[str],
    fetch: Fetcher,
    *,
    extension: bool = True,
    parse: Callable[[str], list] | None = None,
    verify: Callable[[dict], bool] | None = None,
    value_of: Callable[[dict], Decimal] | None = None,
    policy: dict[str, Decimal] | None = None,
) -> AgentRun:
    """One shopper request across every merchant, with the reasoning recorded."""
    policy = policy or DEFAULT_POLICY
    steps: list[Step] = []
    constraints: list[dict] = []

    # --- intent -----------------------------------------------------------
    if parse is None:
        steps.append(Step(Phase.INTENT, Outcome.ABSENT,
                          "No interpreter wired - the request is passed through as a keyword query.",
                          {"utterance": utterance}))
    else:
        parsed = parse(utterance)
        constraints = [{"text": getattr(c, "text", str(c)),
                        "kind": getattr(getattr(c, "kind", None), "value", "unknown")}
                       for c in parsed]
        by_kind: dict[str, int] = {}
        for c in constraints:
            by_kind[c["kind"]] = by_kind.get(c["kind"], 0) + 1
        unanswerable = by_kind.get("SERVICE", 0) + by_kind.get("VALUES", 0)
        steps.append(Step(
            Phase.INTENT, Outcome.OK,
            f"Decoded {len(constraints)} constraints; {unanswerable} of them cannot be "
            f"answered from any catalogue attribute.",
            {"constraints": constraints, "by_kind": by_kind}))

    # --- discovery, negotiation, verification, valuation ------------------
    ranked: list[Ranked] = []
    verifier_missing = verify is None
    any_records = False

    for merchant in merchants:
        try:
            body = fetch(merchant, utterance, extension=extension)
        except PermissionError as exc:  # 406: a legitimate protocol answer
            steps.append(Step(Phase.NEGOTIATION, Outcome.REFUSED,
                              f"{merchant} refused a capability this agent did not declare.",
                              {"merchant": merchant, "detail": str(exc)}))
            continue

        products = body.get("products", [])
        # `extensions` is ABSENT, not empty, when negotiation dropped it.
        ext_blocks = body.get("extensions", {}).get(BENEFIT_EXT)
        steps.append(Step(
            Phase.DISCOVERY, Outcome.OK,
            f"{merchant} returned {len(products)} products"
            + (" with the benefit extension." if ext_blocks is not None else " as plain UCP."),
            {"merchant": merchant, "products": len(products),
             "extension": ext_blocks is not None,
             "capabilities": sorted(body.get("active_capabilities", {}))}))

        if ext_blocks is None and extension:
            steps.append(Step(
                Phase.NEGOTIATION, Outcome.DEGRADED,
                f"{merchant} does not publish the benefit extension - it is ranked on shelf price alone.",
                {"merchant": merchant}))

        # blocks are positional, one per product, but each carries sku_id
        by_sku = {b.get("sku_id"): b for b in (ext_blocks or [])}

        for product in products:
            sku_id = product.get("id")
            shelf = _decimal(product.get("price", {}).get("amount", "0"))
            block = by_sku.get(sku_id, {})
            records = block.get("records", [])
            any_records = any_records or bool(records)

            verified, credited_total, citations = [], Decimal("0"), []
            for entry in records:
                rec = entry.get("record", {})
                btype = rec.get("benefit_type", "unknown")
                # `signed` is derived by the server, but trust is ours to decide.
                ok = False if verifier_missing else bool(verify(entry))
                if ok:
                    verified.append(entry)
                ceiling = rec.get("value_ceiling_aud")
                if ceiling is None:
                    # values claim: validated, citable, worth exactly zero
                    citations.append({"record_id": rec.get("record_id"), "benefit_type": btype,
                                      "credited": "0.00", "cited": ok,
                                      "why": "values claim - validated, never priced"})
                    continue
                if not ok:
                    citations.append({"record_id": rec.get("record_id"), "benefit_type": btype,
                                      "credited": "0.00", "cited": False,
                                      "why": "unverified - displayed, never valued"})
                    continue
                merchant_ceiling = _decimal(ceiling)
                shopper_value = policy.get(btype, Decimal("0"))
                credit = min(merchant_ceiling, shopper_value) if value_of is None else value_of(entry)
                credited_total += credit
                citations.append({"record_id": rec.get("record_id"), "benefit_type": btype,
                                  "credited": f"{credit:.2f}", "cited": True,
                                  "why": f"min(merchant ceiling {merchant_ceiling}, shopper policy {shopper_value})"})

            ranked.append(Ranked(
                merchant=body.get("business", {}).get("id", merchant),
                sku_id=sku_id, title=product.get("title", ""),
                shelf_price=shelf, credited=credited_total,
                effective_cost=shelf - credited_total,
                records_seen=len(records), records_verified=len(verified),
                records_credited=sum(1 for c in citations if c["cited"] and c["credited"] != "0.00"),
                citations=citations,
                withheld_note=None if records else "no machine-readable offer published",
            ))

    # --- verification / valuation honesty ---------------------------------
    if verifier_missing:
        steps.append(Step(
            Phase.VERIFICATION, Outcome.ABSENT,
            "No signature verifier wired - every record is treated as unverified and credited nothing.",
            {"rule": "fail closed"}))
    if not any_records:
        steps.append(Step(
            Phase.VALUATION, Outcome.DEGRADED,
            "No benefit records were published by any merchant, so effective cost equals shelf price.",
            {"rule": "nothing credited without a record"}))

    # --- ranking ----------------------------------------------------------
    ranked.sort(key=lambda r: (r.effective_cost, r.shelf_price))
    if ranked:
        top = ranked[0]
        cheapest_shelf = min(ranked, key=lambda r: r.shelf_price)
        flipped = top.sku_id != cheapest_shelf.sku_id
        steps.append(Step(
            Phase.RANKING, Outcome.OK,
            (f"{top.merchant} wins on effective cost {top.effective_cost:.2f} "
             f"despite a higher shelf price than {cheapest_shelf.merchant}."
             if flipped else
             f"{top.merchant} wins on both shelf price and effective cost - no flip."),
            {"winner": top.sku_id, "flipped": flipped,
             "cheapest_shelf": cheapest_shelf.sku_id}))

    return AgentRun(utterance=utterance, extension_enabled=extension,
                    steps=steps, ranked=ranked, constraints=constraints)
