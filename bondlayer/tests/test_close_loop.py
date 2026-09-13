"""The buyer agent checks out the offer it ranked first (WS-L).

What these tests hold:

- The wrapper is the run plus exactly one step. Ranking, bundles, constraints
  and every pre-existing step are the same objects a run without it carries --
  the order is the outcome of the ranking, never an input to it.
- The body names exactly the records the agent relied on: verified records
  that moved the effective cost or answered a clause. A record that did not
  verify is never sent; neither is one the valuation already scoped out.
- A 406 is a DEGRADED step, never an exception; a refused verdict is DEGRADED
  with the merchant's reason in the summary; a transport error propagates.
- End to end against the real merchant app, every id the agent cites on R01 is
  honoured and comes back as a signed envelope; the control run's order is a
  plain UCP order; the order id is deterministic and differs between the two.
- The CLI prints the section last, in both modes, and everything before it is
  what it was.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bondlayer.agent import run_request
from bondlayer.agent.close_loop import (
    NO_WINNER_SUMMARY,
    STEP_KIND,
    checkout_body,
    cited_record_ids,
    close_loop,
    close_loop_step,
    record_unreachable,
)
from bondlayer.agent.merchant_decode import run_with_merchant_decode
from bondlayer.agent.trace import AgentRun, Outcome, Phase
from bondlayer.interpreter.parser import parse as parse_utterance
from bondlayer.ucp.capabilities import BENEFIT_VALUE, CHECKOUT
from bondlayer.ucp.checkout import STATUS_CONFIRMED
from bondlayer.ucp.server import create_app

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import trace_run  # noqa: E402

R01 = (
    "A laptop under $1,500 I can return easily if it turns out not to suit "
    "my work, from a brand that actually repairs things"
)

#: A record Voltway publishes that verifies, is in scope for a laptop, and is
#: credited on R01. Rejecting it in the verifier makes it ``cited: False``.
DROPPED = "vw-delivery-free-99"
#: Verifies and is cited on the wire, but the valuation scoped it out of a
#: laptop and credited $0 -- the agent did not rely on it.
OUT_OF_SCOPE = "vw-tradein-phone-450"


def _canned(merchant: str, body: dict, *, verdicts: list[dict] | None, extension: bool) -> dict:
    """A WS-K-shaped checkout response, trimmed to what the wrapper reads."""
    response = {
        "business": {"id": merchant, "name": merchant.title()},
        "active_capabilities": {CHECKOUT: "2026-04-08"},
        "order": {
            "order_id": "84373a30a113655c",
            "status": STATUS_CONFIRMED,
            "line_items": [{"sku_id": i["sku_id"], "title": "Laptop", "quantity": i["quantity"],
                            "unit_price": {"amount": "1142.96", "currency": "AUD"},
                            "line_total": {"amount": "1142.96", "currency": "AUD"}}
                           for i in body["items"]],
            "subtotal": {"amount": "1142.96", "currency": "AUD"},
            "payment": {"status": "out_of_scope", "note": "no funds move"},
            "agent_ref": body.get("agent_ref"),
        },
    }
    if extension:
        response["honoured_benefits"] = verdicts if verdicts is not None else [
            {"record_id": rid, "honoured": True, "reason": "verified", "sku_id": body["items"][0]["sku_id"]}
            for rid in body["cited_record_ids"]
        ]
        response["extensions"] = {BENEFIT_VALUE: []}
    return response


class FakeCheckout:
    def __init__(self, *, answer="canned", verdicts=None):
        self.calls: list[tuple[str, dict, bool]] = []
        self.answer = answer
        self.verdicts = verdicts

    def __call__(self, merchant: str, body: dict, *, extension: bool) -> dict | None:
        self.calls.append((merchant, body, extension))
        if self.answer is None:
            return None
        if isinstance(self.answer, BaseException):
            raise self.answer
        return _canned(merchant, body, verdicts=self.verdicts, extension=extension)


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


def _kwargs(client, *, extension: bool, verify=None) -> dict:
    return dict(
        extension=extension,
        verify=verify or trace_run.make_verifier(client, trace_run.MERCHANTS),
        policy=trace_run.POLICY,
        bundler=trace_run.CategoryBundler(),
        **trace_run._interpret_kwargs(parse_utterance),
    )


def _run(client, *, extension: bool, verify=None) -> AgentRun:
    return run_request(R01, trace_run.MERCHANTS, trace_run.make_fetcher(client),
                       **_kwargs(client, extension=extension, verify=verify))


# --- (a) one step appended, the body names what the agent relied on -------------------


def test_one_step_appended_and_nothing_else_touched(client):
    plain = _run(client, extension=True)
    run = _run(client, extension=True)
    fake = FakeCheckout()
    out = close_loop(run, checkout=fake, agent_ref="test")

    assert out is run, "the same run, mutated by one appended step"
    assert run.ranked == plain.ranked
    assert run.bundles == plain.bundles
    assert run.constraints == plain.constraints
    assert run.unsatisfied == plain.unsatisfied
    assert len(run.steps) == len(plain.steps) + 1
    assert run.steps[:-1] == plain.steps

    step = run.steps[-1]
    assert step is close_loop_step(run)
    assert step.phase is Phase.RANKING
    assert step.outcome is Outcome.OK
    assert step.detail["kind"] == STEP_KIND
    assert sum(1 for s in run.steps if s.detail.get("kind") == STEP_KIND) == 1

    # One call, to the winner's merchant, with the toggle state of the run.
    [(merchant, body, extension)] = fake.calls
    assert merchant == run.winner.merchant == "voltway"
    assert extension is True
    assert body["items"] == [{"sku_id": run.winner.sku_id, "quantity": 1}]
    assert body["agent_ref"] == "test"
    assert body == step.detail["request"]
    assert step.detail["merchant"] == "voltway"
    assert step.detail["order"]["order_id"] == "84373a30a113655c"
    assert step.detail["extensions_present"] is True
    n = len(body["cited_record_ids"])
    assert step.detail["summary_counts"] == {"cited": n, "honoured": n}
    assert step.summary == (
        f"Checked out {run.winner.sku_id} at voltway: order 84373a30a113655c confirmed "
        f"(awaiting payment, out of scope); {n} of {n} cited records honoured and bound "
        "into the order."
    )


def test_cited_ids_are_the_records_relied_on_and_never_an_unverified_one(client):
    real = trace_run.make_verifier(client, trace_run.MERCHANTS)

    def verify(entry: dict) -> bool:
        return real(entry) and (entry.get("record") or {}).get("record_id") != DROPPED

    run = _run(client, extension=True, verify=verify)
    w = run.winner
    by_id = {c["record_id"]: c for c in w.citations}
    assert by_id[DROPPED]["cited"] is False, "the verifier rejected it"
    assert by_id[OUT_OF_SCOPE]["cited"] is True and by_id[OUT_OF_SCOPE]["credited"] == "0.00"

    cited = cited_record_ids(w)
    assert cited, "R01 relies on records"
    assert DROPPED not in cited, "an unverified record is never sent"
    assert OUT_OF_SCOPE not in cited, "a record the valuation scoped out was not relied on"
    # Every credited record and every resolver evidence record is in, once.
    credited = [c["record_id"] for c in w.citations if c["cited"] and c["credited"] != "0.00"]
    evidence = [rc.evidence_record_id for rc in w.resolved if rc.evidence_record_id]
    assert set(cited) == set(credited) | set(evidence)
    assert len(cited) == len(set(cited))
    assert "vw-returns-60" in cited and "vw-repairability-parts-5y" in cited

    body = checkout_body(w, None)
    assert body["cited_record_ids"] == cited
    assert "agent_ref" not in body
    # Nothing about the shopper travels: the route forbids extra fields, and
    # this builds only the three the route knows.
    assert set(body) == {"items", "cited_record_ids"}


# --- (b) 406 is a finding, not an exception -------------------------------------------


def test_a_406_is_a_degraded_step_and_never_raises(client):
    run = _run(client, extension=True)
    close_loop(run, checkout=FakeCheckout(answer=None))
    step = close_loop_step(run)
    assert step.outcome is Outcome.DEGRADED
    assert step.detail["order"] is None
    assert step.detail["honoured_benefits"] is None
    assert "did not negotiate dev.ucp.shopping.checkout" in step.summary
    assert "the loop stays open" in step.summary


def test_no_winner_means_nothing_is_sent():
    run = AgentRun(utterance="x", extension_enabled=True, steps=[], ranked=[])
    fake = FakeCheckout()
    close_loop(run, checkout=fake)
    assert fake.calls == []
    [step] = run.steps
    assert step.phase is Phase.RANKING and step.outcome is Outcome.DEGRADED
    assert step.summary == NO_WINNER_SUMMARY
    assert step.detail == {"kind": STEP_KIND, "order": None}


def test_a_transport_error_propagates_and_can_be_recorded(client):
    run = _run(client, extension=True)
    before = len(run.steps)
    with pytest.raises(ConnectionError):
        close_loop(run, checkout=FakeCheckout(answer=ConnectionError("merchant down")))
    assert len(run.steps) == before, "nothing recorded by close_loop itself"
    record_unreachable(run, ConnectionError("merchant down"))
    step = close_loop_step(run)
    assert step.outcome is Outcome.DEGRADED
    assert step.detail["order"] is None
    assert step.detail["error"] == "ConnectionError: merchant down"
    assert "Checkout could not be completed at voltway for VOL-0031 (ConnectionError)" in step.summary


# --- (c) a refused verdict is named ---------------------------------------------------


def test_a_refused_verdict_degrades_the_step_and_names_the_reason(client):
    run = _run(client, extension=True)
    cited = cited_record_ids(run.winner)
    verdicts = [{"record_id": rid, "honoured": True, "reason": "verified", "sku_id": run.winner.sku_id}
                for rid in cited]
    verdicts[0] = {"record_id": cited[0], "honoured": False, "sku_id": None,
                   "reason": "record scope 'phone' does not cover category 'laptop'"}
    close_loop(run, checkout=FakeCheckout(verdicts=verdicts))
    step = close_loop_step(run)
    assert step.outcome is Outcome.DEGRADED
    assert step.detail["summary_counts"] == {"cited": len(cited), "honoured": len(cited) - 1}
    assert f"{len(cited) - 1} of {len(cited)} cited records honoured" in step.summary
    assert f"Not honoured -- {cited[0]}: record scope 'phone' does not cover category 'laptop'." in step.summary


def test_control_wording_when_nothing_was_cited(client):
    run = _run(client, extension=False)
    assert cited_record_ids(run.winner) == []
    close_loop(run, checkout=FakeCheckout())
    step = close_loop_step(run)
    assert step.outcome is Outcome.OK
    assert step.detail["honoured_benefits"] is None
    assert step.detail["extensions_present"] is False
    assert step.summary.endswith("confirmed (awaiting payment, out of scope); no benefit records "
                                 "were cited, so the order binds none.")


# --- (d) end to end against the real merchant app -------------------------------------


def _real(client, *, extension: bool) -> AgentRun:
    run = run_with_merchant_decode(
        R01, trace_run.MERCHANTS, trace_run.make_fetcher(client),
        propose=trace_run.make_proposer(client), **_kwargs(client, extension=extension),
    )
    return close_loop(run, checkout=trace_run.make_checkout(client), agent_ref="test")


def test_end_to_end_r01_extension_on_every_cited_record_is_honoured(client):
    run = _real(client, extension=True)
    assert run.winner.merchant == "voltway"
    step = close_loop_step(run)
    assert step.outcome is Outcome.OK, step.summary
    order = step.detail["order"]
    assert order["status"] == STATUS_CONFIRMED
    assert order["line_items"][0]["sku_id"] == run.winner.sku_id
    assert order["subtotal"]["amount"] == str(run.winner.shelf_price)
    assert order["payment"]["status"] == "out_of_scope"
    assert order["agent_ref"] == "test"

    cited = step.detail["request"]["cited_record_ids"]
    verdicts = step.detail["honoured_benefits"]
    assert cited and [v["record_id"] for v in verdicts] == cited
    assert all(v["honoured"] is True for v in verdicts), verdicts
    assert all(v["sku_id"] == run.winner.sku_id for v in verdicts)
    assert step.detail["extensions_present"] is True
    assert step.detail["summary_counts"] == {"cited": len(cited), "honoured": len(cited)}

    # The envelopes the order carries are the ones the agent verified during
    # discovery: same ids, and the agent's own verifier passes each again.
    header = ";".join([trace_run.CATALOG_SEARCH, trace_run.CATALOG_LOOKUP, CHECKOUT, BENEFIT_VALUE])
    wire = client.post(f"/voltway/ucp/checkout", json=step.detail["request"],
                       headers={"UCP-Agent": header}).json()
    envelopes = wire["extensions"][BENEFIT_VALUE]
    assert sorted(e["record"]["record_id"] for e in envelopes) == sorted(cited)
    verify = trace_run.make_verifier(client, trace_run.MERCHANTS)
    assert all(verify(e) for e in envelopes)


def test_end_to_end_r01_control_is_a_plain_order_for_the_cheapest_shelf(client):
    run = _real(client, extension=False)
    cheapest = min(run.ranked, key=lambda r: r.shelf_price)
    assert run.winner.sku_id == cheapest.sku_id
    step = close_loop_step(run)
    assert step.outcome is Outcome.OK, step.summary
    assert step.detail["request"]["cited_record_ids"] == []
    assert step.detail["honoured_benefits"] is None
    assert step.detail["extensions_present"] is False
    order = step.detail["order"]
    assert order["status"] == STATUS_CONFIRMED
    assert order["line_items"][0]["sku_id"] == cheapest.sku_id
    assert order["subtotal"]["amount"] == str(cheapest.shelf_price)


def test_order_ids_are_deterministic_and_differ_between_the_two_runs(client):
    on_a = close_loop_step(_real(client, extension=True)).detail["order"]["order_id"]
    on_b = close_loop_step(_real(client, extension=True)).detail["order"]["order_id"]
    off = close_loop_step(_real(client, extension=False)).detail["order"]["order_id"]
    assert on_a == on_b, "same run, same content hash"
    assert on_a != off, "a different sku with a different honoured set"


# --- the CLI prints it last, and prints what it printed before ----------------------------


def _cli(*args: str) -> str:
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "trace_run.py"), R01, *args],
        capture_output=True, text=True, timeout=90,
    )
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_cli_prints_the_close_loop_section_last_with_the_extension():
    text = _cli()
    head = "close the loop (POST /ucp/checkout):"
    assert text.index("FLIP:") < text.index("BUNDLE - ") < text.index(head)
    section = text.split(head)[1]
    assert section.strip().endswith("=" * 78)
    assert "voltway      VOL-0031  order " in section
    assert "confirmed_awaiting_payment  subtotal $1,142.96" in section
    assert "payment: out of scope for this prototype; no funds move" in section
    assert "honoured benefits bound into the order (" in section
    assert "✓ vw-returns-60 (free_returns)" in section
    assert "✓ vw-repairability-parts-5y (repairability)" in section
    assert "✗" not in section, "every cited record is honoured on R01"
    # And the step is in the trace as an ordinary step.
    assert "Checked out VOL-0031 at voltway: order " in text


def test_cli_control_prints_a_plain_order():
    text = _cli("--control")
    head = "close the loop (POST /ucp/checkout):"
    assert text.index("NO FLIP:") < text.index(head)
    section = text.split(head)[1]
    assert "citycircuit  CIT-0032  order " in section
    assert "confirmed_awaiting_payment  subtotal $1,066.00" in section
    assert "plain UCP order: no benefit records were cited, so the order binds none." in section
    assert "honoured benefits" not in section
