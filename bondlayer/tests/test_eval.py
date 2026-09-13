"""The evaluation run, asserted.

The numbers in the pitch come from `scripts/eval_run.py`. These tests run the
same code the script runs, so a change that would move a published figure fails
here first rather than in front of a judge.

The two that matter:

- every one of the 30 frozen requests parses and resolves without raising --
  including R30, which is deliberately vague, because the workshop steer was
  that ambiguity returns a best understanding and never a hard failure;
- citation precision is exactly 1.00. That is an assertion about the product,
  not a metric to improve: a cited record that does not verify is a bug.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from bondlayer.interpreter.parser import parse
from bondlayer.interpreter.resolver import UNANSWERED, resolve_detailed
from bondlayer.types import ConstraintKind

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "data" / "eval" / "requests.json"
SCRIPT = ROOT / "scripts" / "eval_run.py"

RECORD_KINDS = (ConstraintKind.SERVICE, ConstraintKind.VALUES)


@pytest.fixture(scope="module")
def runner():
    """Import `scripts/eval_run.py` as a module; it is not on the package path.

    It has to be registered in ``sys.modules`` before it is executed, because
    ``dataclasses`` resolves a field's annotations through the defining
    module and a module that is not registered has none.
    """
    spec = importlib.util.spec_from_file_location("eval_run", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def requests_() -> list[dict]:
    return json.loads(EVAL.read_text(encoding="utf-8"))["requests"]


@pytest.fixture(scope="module")
def catalogue(runner):
    return runner.load_catalogue()


@pytest.fixture(scope="module")
def verified(runner):
    kept, _ = runner.verified_records(runner.load_published(), runner.load_verifiers())
    return kept


@pytest.fixture(scope="module")
def outcomes(runner, requests_, catalogue, verified):
    """Every request scored once, BondLayer and control, as the script does it."""
    valid = {r.record.record_id for r in verified}
    scored = []
    for request in requests_:
        constraints = parse(request["utterance"])
        bond = runner.score(request, resolve_detailed(constraints, catalogue, verified).proposals, valid)
        ctrl = runner.score(request, resolve_detailed(constraints, catalogue, []).proposals, valid)
        scored.append((request, bond, ctrl))
    return scored


# --- the set itself ---------------------------------------------------------


def test_the_frozen_set_is_thirty_requests_and_has_not_been_regenerated(requests_):
    payload = json.loads(EVAL.read_text(encoding="utf-8"))
    assert payload["count"] == len(requests_) == 30
    assert payload["frozen"] == "2026-09-12"
    assert "Do not regenerate" in payload["freeze_rule"]


# --- all thirty parse and resolve -------------------------------------------


def test_all_thirty_parse_and_resolve_without_raising(outcomes):
    for request, bond, _ in outcomes:
        assert bond.proposals, f"{request['id']} returned no proposals at all"


def test_a_vague_request_returns_a_recommendation_not_a_failure(outcomes):
    """R30 is deliberately vague. Taxonomy rule 4: never hard-fail on ambiguity."""
    request, bond, _ = next(o for o in outcomes if o[0]["id"] == "R30")
    assert request["notes"].startswith("Deliberately vague")
    assert bond.proposals
    # And the assumption it made is stated, not hidden.
    assert all(r.note.strip() for p in bond.proposals for r in p.resolved)


def test_no_request_invents_a_constraint_the_shopper_did_not_say(outcomes):
    """R10 has no budget clause at all; a parser that adds one is guessing."""
    request, bond, _ = next(o for o in outcomes if o[0]["id"] == "R10")
    constraints = parse(request["utterance"])
    assert not [c for c in constraints if "$" in c.text]


# --- the five metrics -------------------------------------------------------


def test_citation_precision_is_exactly_one(outcomes):
    """Every cited record exists and verifies. Anything less is a bug."""
    total = sum(b.citations_total for _, b, _ in outcomes)
    valid = sum(b.citations_valid for _, b, _ in outcomes)
    assert total > 0, "nothing was cited, so this proves nothing"
    assert valid == total, f"{total - valid} citations do not verify"


def test_the_control_cites_nothing_at_all(outcomes):
    """No records on the wire means no evidence, and it must not pretend."""
    assert sum(c.citations_total for _, _, c in outcomes) == 0


def test_every_request_expecting_an_unsatisfied_clause_reports_one(outcomes):
    expecting = [(r, b) for r, b, _ in outcomes if r["expect_unsatisfied"]]
    assert expecting, "no request expects an unsatisfied clause"
    for request, bond in expecting:
        assert bond.reports_unsatisfied, f"{request['id']} dropped a clause silently"


def test_gold_recall_does_not_regress(outcomes):
    """A floor, not a target. Moving it down needs an argument in the channel."""
    recalls = [b.gold_recall for _, b, _ in outcomes]
    mean = sum(recalls) / len(recalls)
    assert mean >= 0.99, f"gold recall fell to {mean:.3f}"


def test_hard_precision_does_not_regress(outcomes):
    precisions = [b.hard_precision for _, b, _ in outcomes]
    mean = sum(precisions) / len(precisions)
    assert mean >= 0.87, f"hard precision fell to {mean:.3f}"


# --- the argument the evaluation exists to make -----------------------------


def test_the_control_answers_no_service_or_values_clause(outcomes):
    """The whole claim, in one assertion.

    No product export has a column for "can I return this easily". If the
    control ever answers one of these, either the catalogue grew a column it
    should not have or the resolver is guessing.
    """
    answered = sum(c.clauses_answered for _, _, c in outcomes)
    total = sum(c.clauses_total for _, _, c in outcomes)
    assert total > 0
    assert answered == 0, f"the control answered {answered}/{total} unanswerable clauses"


def test_bondlayer_answers_most_of_them(outcomes):
    answered = sum(b.clauses_answered for _, b, _ in outcomes)
    total = sum(b.clauses_total for _, b, _ in outcomes)
    assert answered / total >= 0.80, f"only {answered}/{total} answered"


def test_the_three_it_cannot_answer_are_honest_about_it(outcomes):
    """No merchant publishes a support-lifetime, carbon-neutral or origin claim.

    Those clauses must come back unsatisfied with the marker, not quietly
    satisfied by the nearest record that happens to share a benefit type.
    """
    unanswered = []
    for request, bond, _ in outcomes:
        wanted = [c for c in parse(request["utterance"]) if c.kind in RECORD_KINDS]
        satisfied = {
            r.constraint.text for p in bond.proposals for r in p.resolved
            if r.constraint.kind in RECORD_KINDS and r.satisfied
        }
        unanswered.extend(
            (request["id"], c.text) for c in wanted if c.text not in satisfied
        )
    assert {rid for rid, _ in unanswered} == {"R16", "R17", "R29"}

    for request, bond, _ in outcomes:
        for proposal in bond.proposals:
            for constraint in proposal.unsatisfied:
                note, = [r.note for r in proposal.resolved
                         if r.constraint.text == constraint.text]
                assert note == UNANSWERED


# --- the run is reproducible ------------------------------------------------


def test_two_runs_of_the_same_request_are_identical(catalogue, verified, requests_):
    """Deterministic: no clock, no random seed, no set iteration order leaking.

    A number that moves between runs cannot go in the pitch.
    """
    for request in requests_[:6]:
        constraints = parse(request["utterance"])
        first = resolve_detailed(constraints, catalogue, verified)
        second = resolve_detailed(constraints, catalogue, verified)
        assert first.sku_ids == second.sku_ids
        assert [[r.note for r in p.resolved] for p in first.proposals] == \
               [[r.note for r in p.resolved] for p in second.proposals]


def test_the_runner_writes_a_report_per_request_shaped_for_the_console(runner, requests_):
    """WS-E renders these four figures; the shape is the contract between us."""
    reports = runner.REPORTS
    if not reports.exists():
        pytest.skip("run `python scripts/eval_run.py` to generate the reports")
    for request in requests_:
        path = reports / f"{request['id']}.json"
        assert path.exists(), f"no report for {request['id']}"
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["request_id"] == request["id"]
        assert payload["merchants"] and payload["control"]
        for row in payload["merchants"]:
            assert set(row) >= {
                "request_id", "fields_exposed", "legible_share",
                "value_credited_aud", "value_withheld_aud", "won", "lost_because",
            }
            assert row["won"] or row["lost_because"], "a loss with no reason given"
        assert sum(1 for row in payload["merchants"] if row["won"]) == 1
