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
    assert trace_run._search_params(R01) == {"category": "laptop", "max_price": 1500.0}


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
