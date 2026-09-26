"""The buyer agent asks the merchant to decode the sentence itself (WS-J).

What these tests hold:

- The wrapper is ``run_request`` plus exactly one step. Ranking, bundles,
  constraints and every pre-existing step are the same objects a plain
  ``run_request`` returns with the same kwargs -- the merchant's reading is
  shown next to the agent's, never fed into it.
- With the extension off nothing is sent: ``propose`` is never called and the
  step says so, DEGRADED.
- The agreement rule is the documented one: same kind and overlapping tokens
  pair, a clause the merchant filed under another kind does not.
- End to end against the real merchant app, every record a merchant cites in
  its proposals is one the agent's own verifier passes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bondlayer.agent import run_request
from bondlayer.agent.merchant_decode import (
    EXTENSION_OFF_SUMMARY,
    STEP_KIND,
    agreement,
    merchant_decode_step,
    run_with_merchant_decode,
    tokens,
)
from bondlayer.agent.trace import Outcome, Phase
from bondlayer.interpreter.parser import parse as parse_utterance
from bondlayer.ucp.capabilities import BENEFIT_VALUE
from bondlayer.ucp.server import create_app

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import trace_run  # noqa: E402

R01 = (
    "A laptop under $1,500 I can return easily if it turns out not to suit "
    "my work, from a brand that actually repairs things"
)

#: The agent's own decode of R01, as ``run_request`` records it.
AGENT_R01 = [
    {"text": "laptop under $1,500", "kind": "hard"},
    {"text": "I can return easily", "kind": "service"},
    {"text": "not to suit my work", "kind": "soft"},
    {"text": "from a brand that actually repairs things", "kind": "values"},
]


def _canned(merchant: str, *, unsatisfied_values: bool) -> dict:
    """A WS-H-shaped intent response, trimmed to what the wrapper reads."""
    resolved = [
        {"text": "laptop under $1,500", "kind": "hard", "satisfied": True,
         "evidence_record_id": None, "evidence_attribute": "shelf_price",
         "note": "Shelf price is within the ceiling."},
        {"text": "I can return easily", "kind": "service", "satisfied": True,
         "evidence_record_id": f"{merchant[:2]}-returns", "evidence_attribute": None,
         "note": "Answered by verified record."},
        {"text": "not to suit my work", "kind": "soft", "satisfied": True,
         "evidence_record_id": None, "evidence_attribute": "ram_gb",
         "note": "Ranked, not filtered."},
        {"text": "from a brand that actually repairs things", "kind": "values",
         "satisfied": not unsatisfied_values,
         "evidence_record_id": None if unsatisfied_values else f"{merchant[:2]}-repair",
         "evidence_attribute": None,
         "note": "← no catalogue attribute answers this" if unsatisfied_values
         else "Answered by verified record."},
    ]
    return {
        "business": {"id": merchant, "name": merchant.title()},
        "active_capabilities": {},
        "decoded_intent": {
            "decoder": "rules",
            "utterance": R01,
            "constraints": [
                {"text": c["text"], "kind": c["kind"], "interpretation": {}}
                for c in AGENT_R01
            ],
            "unanswerable_from_catalogue": 2,
            "assumptions": ["Budget of $1,500.00 read as a hard ceiling."],
            "clarifying_question": None,
        },
        "proposals": [
            {"product": {"id": f"{merchant[:3].upper()}-{n:04d}", "title": f"Laptop {n}",
                         "price": {"amount": f"{1000 + n}.00", "currency": "AUD"},
                         "category": "laptop", "attributes": {}},
             "resolved": resolved,
             "unsatisfied": ([{"text": "from a brand that actually repairs things",
                               "kind": "values"}] if unsatisfied_values else [])}
            for n in range(1, 8)  # seven on the wire; the trace keeps five
        ],
    }


class FakeProposer:
    def __init__(self):
        self.calls: list[tuple[str, str, bool]] = []

    def __call__(self, merchant: str, utterance: str, *, extension: bool) -> dict | None:
        self.calls.append((merchant, utterance, extension))
        if merchant == "voltway":
            return _canned(merchant, unsatisfied_values=False)
        if merchant == "northgear":
            return _canned(merchant, unsatisfied_values=True)
        return None  # citycircuit: 406, did not negotiate


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


def _kwargs(client, *, extension: bool) -> dict:
    return dict(
        extension=extension,
        verify=trace_run.make_verifier(client, trace_run.MERCHANTS),
        policy=trace_run.POLICY,
        bundler=trace_run.CategoryBundler(),
        **trace_run._interpret_kwargs(parse_utterance),
    )


# --- (a) one step appended, nothing else touched ------------------------------------


def test_wrapper_appends_exactly_one_step_and_changes_nothing_else(client):
    fake = FakeProposer()
    plain = run_request(R01, trace_run.MERCHANTS, trace_run.make_fetcher(client),
                        **_kwargs(client, extension=True))
    run = run_with_merchant_decode(R01, trace_run.MERCHANTS, trace_run.make_fetcher(client),
                                   propose=fake, **_kwargs(client, extension=True))

    # Same ranking, same bundles, same decode, same steps -- plus one.
    assert run.ranked == plain.ranked
    assert run.bundles == plain.bundles
    assert run.constraints == plain.constraints
    assert run.unsatisfied == plain.unsatisfied
    assert run.utterance == plain.utterance and run.extension_enabled == plain.extension_enabled
    assert len(run.steps) == len(plain.steps) + 1
    assert run.steps[:-1] == plain.steps

    step = run.steps[-1]
    assert step is merchant_decode_step(run)
    assert step.phase is Phase.INTENT
    assert step.outcome is Outcome.OK
    assert step.detail["kind"] == STEP_KIND
    assert sum(1 for s in run.steps if s.detail.get("kind") == STEP_KIND) == 1

    # Every merchant was asked once, with the sentence verbatim.
    assert [c[0] for c in fake.calls] == trace_run.MERCHANTS
    assert all(c[1] == R01 and c[2] is True for c in fake.calls)


def test_step_detail_carries_one_entry_per_merchant_in_order(client):
    run = run_with_merchant_decode(R01, trace_run.MERCHANTS, trace_run.make_fetcher(client),
                                   propose=FakeProposer(), **_kwargs(client, extension=True))
    decodes = merchant_decode_step(run).detail["merchant_decodes"]
    assert [d["merchant"] for d in decodes] == trace_run.MERCHANTS
    by = {d["merchant"]: d for d in decodes}

    assert by["voltway"]["negotiated"] and by["northgear"]["negotiated"]
    assert not by["citycircuit"]["negotiated"]
    assert by["citycircuit"]["decoded_intent"] is None
    assert by["citycircuit"]["proposals"] == []
    assert by["citycircuit"]["agreement"] == {
        "clauses": [{"agent": c, "merchant": None, "agree": False} for c in AGENT_R01],
        "agreed": 0, "total": 4, "merchant_only": [],
    }

    # The merchant's decode block travels verbatim.
    assert by["voltway"]["decoded_intent"]["decoder"] == "rules"
    assert by["voltway"]["decoded_intent"]["assumptions"] == [
        "Budget of $1,500.00 read as a hard ceiling."]

    # Proposals are trimmed from the wire and capped at five.
    assert len(by["voltway"]["proposals"]) == 5
    top = by["voltway"]["proposals"][0]
    assert set(top) == {"sku_id", "title", "price", "currency", "resolved", "unsatisfied"}
    assert top["sku_id"] == "VOL-0001" and top["price"] == "1001.00"
    assert len(top["resolved"]) == 4 and top["unsatisfied"] == []
    assert by["northgear"]["proposals"][0]["unsatisfied"] == [
        {"text": "from a brand that actually repairs things", "kind": "values"}]

    # R01: both sides ran the same parser, so 4/4 -- and the summary says so.
    for m in ("voltway", "northgear"):
        assert by[m]["agreement"]["agreed"] == 4
        assert by[m]["agreement"]["total"] == 4
        assert all(c["agree"] for c in by[m]["agreement"]["clauses"])
    summary = merchant_decode_step(run).summary
    assert summary == ("2 of 3 merchants decoded the request themselves; both agree with "
                       "the agent on 4/4 clauses. citycircuit did not negotiate intent_match.")


def test_a_proposer_that_raises_degrades_that_merchant_and_keeps_the_run(client):
    def flaky(merchant, utterance, *, extension):
        if merchant == "northgear":
            raise ConnectionError("merchant down")
        return FakeProposer()(merchant, utterance, extension=extension)

    plain = run_request(R01, trace_run.MERCHANTS, trace_run.make_fetcher(client),
                        **_kwargs(client, extension=True))
    run = run_with_merchant_decode(R01, trace_run.MERCHANTS, trace_run.make_fetcher(client),
                                   propose=flaky, **_kwargs(client, extension=True))
    assert run.ranked == plain.ranked
    step = merchant_decode_step(run)
    by = {d["merchant"]: d for d in step.detail["merchant_decodes"]}
    assert by["northgear"]["negotiated"] is False
    assert by["northgear"]["error"] == "ConnectionError: merchant down"
    assert "northgear could not be asked (ConnectionError: merchant down)." in step.summary
    assert step.outcome is Outcome.OK, "voltway still decoded it"


def test_no_merchant_negotiating_is_degraded(client):
    run = run_with_merchant_decode(R01, trace_run.MERCHANTS, trace_run.make_fetcher(client),
                                   propose=lambda *a, **k: None,
                                   **_kwargs(client, extension=True))
    step = merchant_decode_step(run)
    assert step.outcome is Outcome.DEGRADED
    assert step.summary.startswith("0 of 3 merchants decoded the request themselves.")
    assert "voltway, citycircuit, northgear did not negotiate intent_match." in step.summary


# --- (b) extension off: nothing is sent -----------------------------------------------


def test_extension_off_never_calls_propose_and_says_so(client):
    fake = FakeProposer()
    plain = run_request(R01, trace_run.MERCHANTS, trace_run.make_fetcher(client),
                        **_kwargs(client, extension=False))
    run = run_with_merchant_decode(R01, trace_run.MERCHANTS, trace_run.make_fetcher(client),
                                   propose=fake, **_kwargs(client, extension=False))
    assert fake.calls == []
    assert run.ranked == plain.ranked
    assert run.steps[:-1] == plain.steps
    step = run.steps[-1]
    assert step.phase is Phase.INTENT
    assert step.outcome is Outcome.DEGRADED
    assert step.summary == EXTENSION_OFF_SUMMARY
    assert step.detail == {"kind": STEP_KIND, "merchant_decodes": []}


# --- (c) the agreement rule ---------------------------------------------------------------


def test_tokens_drop_function_words_only():
    assert tokens("I can return easily") == {"can", "return", "easily"}
    assert tokens("A laptop under $1,500") == {"laptop", "under", "1", "500"}
    assert tokens("the") == frozenset()


def test_agreement_pairs_identical_decodes_four_for_four():
    out = agreement(AGENT_R01, AGENT_R01)
    assert out["agreed"] == 4 and out["total"] == 4
    assert all(c["agree"] and c["merchant"] == c["agent"] for c in out["clauses"])
    assert out["merchant_only"] == []


def test_agreement_reports_a_clause_the_merchant_filed_under_another_kind():
    merchant = [dict(c) for c in AGENT_R01]
    # The merchant read the repairability clause as a SOFT preference.
    merchant[3] = {"text": "from a brand that actually repairs things", "kind": "soft"}
    out = agreement(AGENT_R01, merchant)
    assert out["agreed"] == 3 and out["total"] == 4
    by_text = {c["agent"]["text"]: c for c in out["clauses"]}
    values = by_text["from a brand that actually repairs things"]
    assert values["agree"] is False and values["merchant"] is None
    # The other three still pair, in kind and in text.
    for text in ("laptop under $1,500", "I can return easily", "not to suit my work"):
        assert by_text[text]["agree"] is True
    # The merchant's re-filed clause is reported, not silently dropped.
    assert out["merchant_only"] == [merchant[3]]


def test_agreement_tolerates_a_shorter_reading_of_the_same_clause():
    # Subset of tokens: "return easily" is inside "I can return easily".
    out = agreement([{"text": "I can return easily", "kind": "service"}],
                    [{"text": "return easily", "kind": "service"}])
    assert out["agreed"] == 1
    # Same kind, different words: no pair.
    out = agreement([{"text": "I can return easily", "kind": "service"}],
                    [{"text": "two year warranty", "kind": "service"}])
    assert out["agreed"] == 0 and out["clauses"][0]["merchant"] is None


def test_agreement_is_greedy_on_highest_overlap_and_uses_each_clause_once():
    agent = [{"text": "light enough to carry", "kind": "soft"},
             {"text": "light", "kind": "soft"}]
    merchant = [{"text": "light", "kind": "soft"},
                {"text": "light enough to carry every day", "kind": "soft"}]
    out = agreement(agent, merchant)
    assert out["agreed"] == 2
    assert out["clauses"][0]["merchant"]["text"] == "light enough to carry every day"
    assert out["clauses"][1]["merchant"]["text"] == "light"


# --- (d) end to end against the real merchant app --------------------------------------------


def test_end_to_end_r01_every_cited_record_verifies_with_the_agents_own_verifier(client):
    verify = trace_run.make_verifier(client, trace_run.MERCHANTS)
    run = run_with_merchant_decode(
        R01, trace_run.MERCHANTS, trace_run.make_fetcher(client),
        propose=trace_run.make_proposer(client), **_kwargs(client, extension=True),
    )
    step = merchant_decode_step(run)
    assert step.outcome is Outcome.OK
    by = {d["merchant"]: d for d in step.detail["merchant_decodes"]}
    assert by["voltway"]["negotiated"] and by["northgear"]["negotiated"]
    assert not by["citycircuit"]["negotiated"]

    for m in ("voltway", "northgear"):
        assert by[m]["agreement"]["agreed"] == 4 == by[m]["agreement"]["total"]
        assert by[m]["decoded_intent"]["decoder"] == "rules"
        assert len(by[m]["decoded_intent"]["constraints"]) == 4
        assert by[m]["proposals"], m

        # The records each proposal cites, checked against the merchant's own
        # published key by the agent's verifier -- the same gate the ranking uses.
        header = ";".join([trace_run.CATALOG_SEARCH, trace_run.CATALOG_LOOKUP,
                           trace_run.BENEFIT_VALUE, trace_run.INTENT_MATCH])
        wire = client.post(f"/{m}/ucp/intent/propose", json={"utterance": R01, "limit": 5},
                           headers={"UCP-Agent": header}).json()
        served: dict[str, dict] = {}
        for block in wire["extensions"][BENEFIT_VALUE]:
            for entry in block["records"]:
                served[entry["record"]["record_id"]] = entry
        cited = {r["evidence_record_id"] for p in by[m]["proposals"]
                 for r in p["resolved"] if r["evidence_record_id"]}
        assert cited, f"{m} cites at least one record on R01"
        for record_id in cited:
            assert verify(served[record_id]) is True, record_id

    # The merchant's proposals never leak into the ranking: the winner is the
    # agent's, and it is not the first item on the merchant's own list.
    assert run.winner.sku_id == "VOL-0031"
    assert by["voltway"]["proposals"][0]["sku_id"] != run.winner.sku_id

    # Voltway answers every clause; NorthGear publishes no repairability record
    # and its proposals say so rather than leaving the clause out.
    assert by["voltway"]["proposals"][0]["unsatisfied"] == []
    assert by["northgear"]["proposals"][0]["unsatisfied"] == [
        {"text": "from a brand that actually repairs things", "kind": "values"}]


def test_cli_prints_the_merchant_decode_section_between_constraints_and_steps():
    import subprocess

    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "trace_run.py"), R01],
        capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 0, out.stderr
    text = out.stdout
    assert text.index("constraints parsed:") < text.index("merchant decode (POST /ucp/intent/propose):") < text.index("steps:")
    section = text.split("merchant decode (POST /ucp/intent/propose):")[1].split("steps:")[0]
    assert "voltway      negotiated  4 constraints  agrees with agent 4/4" in section
    assert "northgear    negotiated  4 constraints  agrees with agent 4/4" in section
    assert "unsatisfied: from a brand that actually repairs things" in section
    assert "citycircuit  did not negotiate org.bondlayer.intent_match -- decoded nothing" in section
    assert "assumes: Budget of $1,500.00 read as a hard ceiling" in section
    # The record-only lines are wrapped at 78 columns like every other prose
    # line, so compare on collapsed whitespace.
    flat = " ".join(section.split())
    assert ("record-only: 'I can return easily' can only be answered by a verified "
            "free_returns record") in flat
    assert ("record-only: 'from a brand that actually repairs things' can only be "
            "answered by a verified repairability record") in flat
    # The console's own marker never appears in this section: the merchant's
    # sentences that would have echoed its words are rendered structurally.
    assert "no catalogue attribute" not in section
    # The step is in the trace too, as an ordinary step.
    assert "2 of 3 merchants decoded the request themselves" in text


def test_cli_control_says_the_sentence_was_not_sent():
    import subprocess

    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "trace_run.py"), R01, "--control"],
        capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 0, out.stderr
    section = out.stdout.split("merchant decode (POST /ucp/intent/propose):")[1].split("steps:")[0]
    assert "Extension off: the shopper's sentence was not sent to any merchant" in section
    assert "negotiated" not in section
    assert "/ucp/intent/propose" not in section.replace("(POST /ucp/intent/propose)", "")
