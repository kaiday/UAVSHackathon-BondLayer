"""The buyer agent checks out the offer it ranked first (WS-L).

FPT's desired outcome ends with step 5, *"closing the loop through a seamless,
API-driven transaction"*. The merchant side has had it since WS-K: ``POST
/{merchant}/ucp/checkout`` (``ucp/checkout.py``) turns a chosen offer into an
order confirmation that re-judges, on the merchant's side, every record the
agent cited and binds the ones that hold. Until now nothing on the agent side
called it in the demo, so the judged trace stopped at the ranking.

This module is the buyer agent placing that order. ``close_loop`` takes the
``AgentRun`` the ranking produced and checks out ``run.winner`` -- one unit of
the winning SKU, at the winning merchant, citing **exactly** the record ids the
agent relied on -- and records the merchant's confirmation as **one more
Step** on the trace.

Three things it never does:

- It never changes the ranking. ``run.ranked``, ``run.bundles``,
  ``run.constraints`` and every step already on the run are the objects the
  caller handed in; this appends one ``Step`` to ``run.steps`` and touches
  nothing else. The order is the *outcome* of the ranking, never an input to it.
- It never cites a record that did not verify. ``cited_record_ids`` is built
  from the winner's ``citations`` with ``cited == True`` -- and ``cited`` is set
  by ``composition.run_request`` iff the caller's own verifier passed the
  envelope. An unsigned record is seen on the wire, credited nothing, and never
  reaches the merchant as something the agent relied on.
- It never fabricates a confirmation. A 406 (the merchant did not negotiate
  ``dev.ucp.shopping.checkout``) is recorded as a DEGRADED step with
  ``order: None``; a cited id the merchant refuses to honour is recorded with
  the merchant's own reason. Transport errors propagate: a merchant that is
  down is not a finding this module is entitled to paper over.

``Phase.RANKING`` is reused rather than a new phase added, because
``trace.py`` grows no new Phase on a feature branch; renderers find the step by
``detail["kind"] == "close_loop"``.

No network call beyond whatever the caller's ``checkout`` does -- localhost
HTTP to the merchant in the product; no model call; deterministic (the
merchant's ``order_id`` is a content hash, so the same run yields the same id).
"""

from __future__ import annotations

from typing import Protocol

from bondlayer.agent.trace import AgentRun, Outcome, Phase, Ranked, Step

#: ``Step.detail["kind"]``. Renderers find this step by it.
STEP_KIND = "close_loop"

#: Rendered when there is nothing to check out.
NO_WINNER_SUMMARY = "No winning offer, so nothing to check out."


class Checkout(Protocol):
    """Places one order with one merchant.

    POSTs ``body`` to ``/{merchant}/ucp/checkout`` with the same ``UCP-Agent``
    header logic as the fetcher, and returns the parsed JSON; ``None`` on HTTP
    406 (checkout was not negotiated); raises on any other transport error.
    """

    def __call__(self, merchant: str, body: dict, *, extension: bool) -> dict | None: ...


def cited_record_ids(winner: Ranked) -> list[str]:
    """The record ids the agent relied on for this offer, deduplicated, in order.

    "Relied on" means one of two things, both read off the run and never
    re-decided here:

    - the record **moved the number**: ``citations[].cited`` and a non-zero
      ``credited`` -- the valuation credited it, so it is part of the effective
      cost that ranked this offer first; or
    - the record **answered a clause**: it is the ``evidence_record_id`` of one
      of the offer's ``resolved`` constraints -- the resolver cited it for
      something the shopper said, whether or not it carries a price.

    ``cited`` is ``True`` iff the caller's own verifier passed the envelope
    (``composition.run_request``), and the resolver is handed only verified
    records, so an unverified record can never be in this list. A record that
    verified but was credited $0 and answered nothing -- a scope the valuation
    already ruled out for this category, or a fact no clause asked about -- was
    not relied on for anything, and is not sent as if it had been.
    """
    evidence = {rc.evidence_record_id for rc in winner.resolved if rc.evidence_record_id}
    out: list[str] = []
    for c in winner.citations:
        record_id = c.get("record_id")
        if not record_id or not c.get("cited"):
            continue
        moved = str(c.get("credited", "0.00")) not in ("0.00", "0", "")
        if (moved or record_id in evidence) and record_id not in out:
            out.append(record_id)
    for record_id in (rc.evidence_record_id for rc in winner.resolved):
        if record_id and record_id not in out:
            out.append(record_id)
    return out


def checkout_body(winner: Ranked, agent_ref: str | None) -> dict:
    """The exact body sent to the merchant: sku ids, quantities, cited ids,
    and an opaque reference. Nothing about the shopper's policy has a field
    to travel in -- the route forbids extra fields, and this builds none."""
    body: dict = {
        "items": [{"sku_id": winner.sku_id, "quantity": 1}],
        "cited_record_ids": cited_record_ids(winner),
    }
    if agent_ref is not None:
        body["agent_ref"] = agent_ref
    return body


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def summarise(winner: Ranked, body: dict, response: dict | None) -> tuple[Outcome, str, dict]:
    """The step's outcome, its one-line summary and its detail, from the
    merchant's answer. Pure, so the wording is pinned by test."""
    cited = list(body["cited_record_ids"])
    detail: dict = {
        "kind": STEP_KIND,
        "merchant": winner.merchant,
        "request": body,
        "order": None,
        "honoured_benefits": None,
        "extensions_present": False,
        "summary_counts": {"cited": len(cited), "honoured": 0},
    }

    if response is None:
        return (
            Outcome.DEGRADED,
            f"{winner.merchant} did not negotiate dev.ucp.shopping.checkout, so "
            f"{winner.sku_id} could not be checked out; the ranking stands, the loop stays open.",
            detail,
        )

    order = response.get("order") or {}
    verdicts = response.get("honoured_benefits")
    honoured = [v for v in (verdicts or []) if v.get("honoured")]
    refused = [v for v in (verdicts or []) if not v.get("honoured")]
    detail.update({
        "order": order,
        "honoured_benefits": verdicts,
        "extensions_present": "extensions" in response,
        "summary_counts": {"cited": len(cited), "honoured": len(honoured)},
    })

    head = (
        f"Checked out {winner.sku_id} at {winner.merchant}: order "
        f"{order.get('order_id', '?')} {_status_words(order.get('status'))}"
    )
    if not cited:
        return (
            Outcome.OK,
            head + "; no benefit records were cited, so the order binds none.",
            detail,
        )
    if verdicts is None:
        # The extension did not survive negotiation, so the merchant judged the
        # ids (the order id still binds what it honoured) but returned no
        # verdicts. Say so rather than guess at them.
        return (
            Outcome.OK,
            head + f"; {len(cited)} cited {_plural(len(cited), 'record', 'records')} "
            "sent, verdicts not returned without the benefit extension.",
            detail,
        )
    tail = (
        f"; {len(honoured)} of {len(cited)} cited {_plural(len(cited), 'record', 'records')} "
        "honoured and bound into the order"
    )
    if refused:
        reasons = "; ".join(f"{v.get('record_id')}: {v.get('reason', 'no reason given')}" for v in refused)
        return Outcome.DEGRADED, head + tail + f". Not honoured -- {reasons}.", detail
    return Outcome.OK, head + tail + ".", detail


def _status_words(status: str | None) -> str:
    if status == "confirmed_awaiting_payment":
        return "confirmed (awaiting payment, out of scope)"
    return str(status or "returned")


def close_loop(run: AgentRun, *, checkout: Checkout, agent_ref: str | None = None) -> AgentRun:
    """Check out ``run.winner`` and append the confirmation as one step.

    Everything on ``run`` is returned as it was; one ``Step`` is appended to
    ``run.steps`` with ``detail["kind"] == "close_loop"``. With no winner the
    step says so and nothing is sent. A 406 is a DEGRADED step, never an
    exception; any other transport error propagates.
    """
    winner = run.winner
    if winner is None:
        run.steps.append(Step(Phase.RANKING, Outcome.DEGRADED, NO_WINNER_SUMMARY,
                              {"kind": STEP_KIND, "order": None}))
        return run

    body = checkout_body(winner, agent_ref)
    response = checkout(winner.merchant, body, extension=run.extension_enabled)
    outcome, summary, detail = summarise(winner, body, response)
    run.steps.append(Step(Phase.RANKING, outcome, summary, detail))
    return run


def record_unreachable(run: AgentRun, exc: BaseException) -> AgentRun:
    """Record that the checkout leg could not be completed, as a DEGRADED step.

    ``close_loop`` lets transport errors propagate -- a merchant that is down
    is not this module's to paper over. A caller that owns a real network
    connection (the chat app) catches them and records the failure here, so
    the ranking it already has is still returned with an honest last step,
    instead of a 500 that loses the whole run.
    """
    winner = run.winner
    where = f"{winner.merchant} for {winner.sku_id}" if winner else "the merchant"
    run.steps.append(Step(
        Phase.RANKING, Outcome.DEGRADED,
        f"Checkout could not be completed at {where} ({type(exc).__name__}); "
        "the ranking stands, the loop stays open.",
        {"kind": STEP_KIND, "order": None, "honoured_benefits": None,
         "error": f"{type(exc).__name__}: {exc}"},
    ))
    return run


def close_loop_step(run: AgentRun) -> Step | None:
    """The step this module appended, or ``None`` when the run has none."""
    for step in run.steps:
        if step.detail.get("kind") == STEP_KIND:
            return step
    return None
