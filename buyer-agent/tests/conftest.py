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

BUYER_AGENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BUYER_AGENT))
sys.path.insert(0, str(BUYER_AGENT.parent / "bondlayer" / "src"))

from src.agent import llm  # noqa: E402


def _skus_in_prompt(prompt: str) -> list[str]:
    """The sku ids from the offer payload, in the order the model was shown them."""
    match = re.search(r"Offers:\n(\[.*?\])\n\nRank", prompt, re.DOTALL)
    if match:
        try:
            return [o["sku_id"] for o in json.loads(match.group(1))]
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    # Fall back to scanning, so a payload-shape change degrades to a weaker
    # stub rather than to an empty ranking that silently drops every offer.
    return re.findall(r'"sku_id":\s*"([^"]+)"', prompt)


@pytest.fixture
def stub_model(monkeypatch):
    """Install the stub. Call it to configure this test's model answers.

    ``order`` overrides the ranking, best first, by sku id; any offer it omits
    keeps its original relative position behind the ones it names.
    """

    def install(*, intent=None, order=None, recommendation="A stubbed recommendation.",
                route=None):
        def fake_complete_json(label, system, prompt):
            if label == "intent_parse":
                return intent if intent is not None else {
                    "summary": "stub intent", "category": None,
                    "max_price_aud": None, "must_have": [],
                }
            if label == "rank":
                skus = _skus_in_prompt(prompt)
                if order is not None:
                    skus = [s for s in order if s in skus] + [s for s in skus if s not in order]
                return {
                    "ranking": [
                        {"rank": i, "sku_id": s, "decisive_terms": [],
                         "reasoning": f"stub reasoning for {s}"}
                        for i, s in enumerate(skus, start=1)
                    ],
                    "recommendation": recommendation,
                }
            if label == "route":
                return route if route is not None else {
                    "action": "search", "utterance": "stub utterance",
                }
            raise AssertionError(f"unexpected model call: {label}")

        monkeypatch.setattr(llm, "complete_json", fake_complete_json)
        monkeypatch.setattr(llm, "chat", lambda label, system, messages: "stub chat reply")

    return install
