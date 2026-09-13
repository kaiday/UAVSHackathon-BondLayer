"""The Part-B demo, and the backup for Path A.

Runs the real merchant app in-process (``TestClient``, no network) and checks
the property the whole pitch depends on: the extension changes who wins, and
nothing else about the run does.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from bondlayer.agent import run_request
from bondlayer.interpreter.parser import parse as parse_utterance
from bondlayer.ucp.server import create_app

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import trace_run  # noqa: E402

R01 = (
    "A laptop under $1,500 I can return easily if it turns out not to suit "
    "my work, from a brand that actually repairs things"
)


def _run(extension: bool):
    client = TestClient(create_app())
    return run_request(
        R01,
        trace_run.MERCHANTS,
        trace_run.make_fetcher(client),
        extension=extension,
        verify=trace_run.make_verifier(client, trace_run.MERCHANTS),
        policy=trace_run.POLICY,
        **trace_run._interpret_kwargs(parse_utterance),
    )


def test_search_params_decode_category_and_price_ceiling():
    # `limit` rides along on every query: the route defaults to 20, which
    # silently truncates the shelf a bundle has to be composed from.
    assert trace_run._search_params(R01) == {
        "category": "laptop", "max_price": 1500.0, "limit": trace_run.PAGE,
    }


def test_voltway_wins_with_the_extension():
    run = _run(extension=True)
    assert run.winner is not None
    assert run.winner.merchant == "voltway"
    # Credited value came from records that actually verified.
    assert run.winner.records_verified > 0
    assert run.winner.credited > 0


def test_trace_and_valuation_agree_on_r01():
    """One valuation path (ruling D4): the trace shows the library's number.

    VOL-0031, $1,142.96 shelf, wins R01 at $933.01 effective -- the same cent
    ``test_flip`` and ``docs/eval-results.md`` report. Replaces the
    known-gap pin ($863.01) that documented composition.py's inline crediting
    before WS-A routed it through ``DeterministicValuation``.
    """
    from decimal import Decimal

    run = _run(extension=True)
    assert run.winner.sku_id == "VOL-0031"
    assert run.winner.effective_cost == Decimal("933.01")


def test_voltway_does_not_win_in_control():
    run = _run(extension=False)
    assert run.winner is not None
    assert run.winner.merchant != "voltway"
    assert run.winner.credited == 0
    assert all(r.credited == 0 for r in run.ranked)


def test_verifier_rejects_a_tampered_record(monkeypatch):
    """The verifier is real cryptography, not a stub that trusts ``signed``."""
    client = TestClient(create_app())
    verify = trace_run.make_verifier(client, trace_run.MERCHANTS)
    response = client.get("/voltway/ucp/catalog/search", params={"category": "laptop"},
                          headers={"UCP-Agent": "dev.ucp.shopping.catalog.search;"
                                                 "dev.ucp.shopping.catalog.lookup;"
                                                 "org.bondlayer.benefit_value"})
    body = response.json()
    block = body["extensions"]["org.bondlayer.benefit_value"][0]
    entry = dict(block["records"][0])
    assert verify(entry) is True
    tampered = {**entry, "signature": "AAAA" + entry["signature"][4:]}
    assert verify(tampered) is False
    unsigned = {**entry, "signature": None, "key_id": None}
    assert verify(unsigned) is False


def test_cli_end_to_end_R01_flips_with_the_extension_only():
    """Exactly the command the brief's done-when names, run as a subprocess."""
    script = SCRIPTS / "trace_run.py"

    on = subprocess.run(
        [sys.executable, str(script), R01], capture_output=True, text=True, timeout=60,
    )
    assert on.returncode == 0, on.stderr
    assert "voltway wins on effective cost" in on.stdout
    assert "FLIP:" in on.stdout

    off = subprocess.run(
        [sys.executable, str(script), R01, "--control"], capture_output=True, text=True, timeout=60,
    )
    assert off.returncode == 0, off.stderr
    assert "citations for the winner (voltway" not in off.stdout
    assert "NO FLIP:" in off.stdout


# --- the justification on screen (WS-A2) ------------------------------------
#
# The CLI is the Path-B demo, so what a judge reads for criterion 1 is this
# stdout. These assert the two halves of the argument: with the extension the
# trace names the records that answer the shopper's clauses, and without it the
# same clauses carry the marker and nothing is cited.


def _cli(*args):
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "trace_run.py"), *args],
        capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_cli_names_the_records_that_answer_the_service_and_values_clauses():
    """The line the whole criterion turns on, on stage, in the extension run."""
    from bondlayer.interpreter.resolver import UNANSWERED

    out = _cli(R01)

    assert "why these match" in out
    # "I can return it easily" and "a brand that actually repairs things",
    # answered by name -- not implied by a cheaper number.
    assert "vw-returns-60" in out
    assert "vw-repairability-parts-5y" in out
    assert "cites record vw-returns-60" in out
    assert "cites record vw-repairability-parts-5y" in out
    # HARD is answered by a catalogue column, and the trace says which.
    assert "on attribute shelf_price" in out
    # CityCircuit publishes neither record, and the trace says so twice rather
    # than quietly leaving the clauses out.
    citycircuit = _why_section(out).split("citycircuit CIT-0032")[1]
    assert citycircuit.count(UNANSWERED) == 2


def _why_section(out: str) -> str:
    """Just the per-constraint justification block, without the bundle below."""
    return out.split("why these match")[1].split("citations for the winner")[0]


def test_cli_control_marks_every_unanswerable_clause_and_cites_nothing():
    from bondlayer.interpreter.resolver import UNANSWERED

    out = _cli(R01, "--control")

    assert UNANSWERED in out
    # Three merchants, two unanswerable clauses each, and no record anywhere.
    assert _why_section(out).count(UNANSWERED) == 6
    assert "cites record" not in out
    assert "vw-returns-60" not in out
    assert "vw-repairability-parts-5y" not in out


def test_the_marker_is_never_broken_across_lines():
    """It is a fixed string the console renders verbatim (WS-A brief).

    Wrapping it mid-phrase would make it ungreppable, unquotable in the deck,
    and different from what Minh's dashboard renders.
    """
    from bondlayer.interpreter.resolver import UNANSWERED

    for out in (_cli(R01), _cli(R01, "--control")):
        marker_lines = [ln for ln in out.splitlines() if "no catalogue attribute" in ln]
        assert marker_lines
        assert all(ln.strip() == UNANSWERED for ln in marker_lines)


def test_run_request_attaches_the_resolution_to_every_ranked_offer():
    """Not just the winner: the comparison is the argument."""
    run = _run(extension=True)
    assert all(offer.resolved for offer in run.ranked)
    winner_records = {r.evidence_record_id for r in run.winner.resolved
                      if r.evidence_record_id}
    assert {"vw-returns-60", "vw-repairability-parts-5y"} <= winner_records
