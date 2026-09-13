"""Explicit fixture data for the historical protocol regression tests, and a
stand-in for the model so those tests can run offline.

The model decides the ranking now, so a test with no provider has nothing to
assert about. Rather than deleting those assertions, ``stub_model`` patches
:func:`llm.complete_json` and hands back an answer in the shape the real model
is asked for.

The ranking stub deliberately returns the offers **in the order it was given
them** -- which is ``run_request``'s deterministic order. So a stubbed run
reproduces the arithmetic's winner exactly, and every existing assertion about
who wins still holds. What the tests then pin is the wiring: that the decode
reaches the search, that the model's order is what ``run.ranked`` ends up in,
and that the checkout follows it. A test that wants the model to disagree with
the arithmetic says so explicitly, with ``order=``.
"""

import json
import os
import re
import sys
from pathlib import Path

import pytest

# Set before anything imports bondlayer: the protocol regression tests read a
# fixed catalogue rather than whatever has been onboarded.
os.environ["BONDLAYER_TEST_DATA"] = "1"
os.environ["BONDLAYER_AI_MODE"] = "rules"
os.environ["BONDLAYER_SERVICE_TOKEN"] = "bondlayer-test-service-token"

BUYER_AGENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BUYER_AGENT))
sys.path.insert(0, str(BUYER_AGENT.parent / "bondlayer" / "src"))

from src.agent import llm, rank  # noqa: E402
from bondlayer import ai, activity  # noqa: E402
from bondlayer.interpreter.parser import parse  # noqa: E402


@pytest.fixture(autouse=True)
def offline_transport_and_history(monkeypatch, tmp_path):
    def blocked(*args, **kwargs):
        raise AssertionError("Tests must stub OpenAI transport; live calls are disabled")
    monkeypatch.setattr(ai, "OpenAI", blocked)
    monkeypatch.setattr(activity, "UPLOADS", tmp_path)


def _offers_in_prompt(prompt: str) -> list[dict]:
    """The merchant/SKU identities from the offer payload, in input order."""
    match = re.search(r"Offers:\n(\[.*?\])\n\nRank", prompt, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    raise AssertionError("No offer payload in rank prompt")


@pytest.fixture
def stub_model(monkeypatch):
    """Install the stub. Call it to configure this test's model answers.

    ``order`` overrides the ranking, best first, by sku id; any offer it omits
    keeps its original relative position behind the ones it names.
    """

    def install(*, intent=None, order=None, recommendation="A stubbed recommendation.",
                route=None):
        monkeypatch.setenv("BONDLAYER_AI_MODE", "openai")
        monkeypatch.setattr(rank, "decode", lambda utterance: (
            parse(utterance), {"provider": "stub", "model": "test", "response_id": "stub-intent"}))
        if intent is not None:
            original = rank.parse_intent
            monkeypatch.setattr(rank, "parse_intent", lambda utterance: {**original(utterance), **intent})
        def fake_complete_json(label, system, prompt):
            if label == "rank":
                offers = _offers_in_prompt(prompt)
                if order is not None:
                    offers = sorted(offers, key=lambda o: order.index(o["sku_id"]) if o["sku_id"] in order else len(order))
                return {
                    "ranking": [
                        {"rank": i, "sku_id": o["sku_id"], "merchant": o["merchant"], "decisive_terms": [],
                         "reasoning": f"stub reasoning for {o['sku_id']}"}
                        for i, o in enumerate(offers, start=1)
                    ],
                    "recommendation": recommendation,
                    "ai": {"provider": "stub", "model": "test", "response_id": "stub-rank"},
                }
            if label == "route":
                return route if route is not None else {
                    "action": "search", "utterance": "stub utterance",
                }
            raise AssertionError(f"unexpected model call: {label}")

        monkeypatch.setattr(llm, "complete_json", fake_complete_json)
        monkeypatch.setattr(llm, "chat", lambda label, system, messages: "stub chat reply")

    return install
