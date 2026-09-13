"""The decode-accuracy metric, pinned.

FPT's top-weighted criterion is how well the system *decodes* the shopper's
need. `scripts/eval_run.py` scores `interpreter.parse(utterance)` against the
human-labelled `constraints` in the frozen request set; these tests pin the
matcher's rules on hand-written pairs, run it over all 30 frozen requests, and
prove it is deterministic.

Nothing here touches the parser, the gold, or `types.py`. If the parser drifts,
the numbers here move and the floors below say so.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from bondlayer.interpreter.parser import parse
from bondlayer.types import Constraint, ConstraintKind

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "data" / "eval" / "requests.json"
REPORTS = ROOT / "data" / "eval" / "reports"
SCRIPT = ROOT / "scripts" / "eval_run.py"


@pytest.fixture(scope="module")
def runner():
    """Import `scripts/eval_run.py` as a module under its own name.

    Registered in ``sys.modules`` before execution so dataclass annotations
    resolve; a distinct name so it never collides with `test_eval.py`'s import.
    """
    spec = importlib.util.spec_from_file_location("eval_run_decode", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def requests_() -> list[dict]:
    return json.loads(EVAL.read_text(encoding="utf-8"))["requests"]


def gold(*pairs: tuple[str, str]) -> list[dict]:
    return [{"text": text, "kind": kind} for text, kind in pairs]


def parsed(*pairs: tuple[str, str]) -> list[Constraint]:
    return [Constraint(text=text, kind=ConstraintKind(kind)) for text, kind in pairs]


# --- the tokeniser and stemmer, stated and pinned ---------------------------


def test_tokens_drop_the_stated_stopwords_and_stem_two_ways(runner):
    tokens = runner._decode_tokens
    assert tokens("I can return it easily") == {"can", "return", "easily"}
    assert tokens("a brand that actually repairs things") == {"brand", "actually", "repair", "thing"}
    # One trailing "ing" comes off only when three letters remain: "editing"
    # loses it, "thing" keeps it. Otherwise one trailing "s" comes off.
    assert tokens("for video editing") == {"for", "video", "edit"}
    assert tokens("16 gigs") == {"16", "gig"}
    assert tokens("under $1,500") == {"under", "1", "500"}
    assert runner.DECODE_STOPWORDS == {
        "a", "an", "the", "i", "it", "to", "my", "that", "if", "from", "and", "is", "of",
    }


# --- the matcher on hand-written pairs --------------------------------------


def test_a_perfect_decode_including_the_r01_stem_drift(runner):
    """R01's known drift: gold "suits my work", parser "not to suit my work"."""
    d = runner.decode_score(
        gold(("under $1,500", "HARD"), ("suits my work", "SOFT"),
             ("I can return it easily", "SERVICE")),
        parsed(("laptop under $1,500", "hard"), ("I can return easily", "service"),
               ("not to suit my work", "soft")),
    )
    assert d.precision == 1.0 and d.recall == 1.0
    assert d.kind_confusions == [] and d.misses == [] and d.extras == []
    assert d.perfect
    assert [(p["gold"], p["parsed"]) for p in d.pairs] == [
        ("under $1,500", "laptop under $1,500"),
        ("suits my work", "not to suit my work"),
        ("I can return it easily", "I can return easily"),
    ]


def test_a_kind_confusion_is_a_miss_and_an_extra_and_is_named(runner):
    """R14's shape: same words, wrong kind. Kind-aware scoring misses it; the
    text-only pass says exactly which kind was swapped for which."""
    d = runner.decode_score(
        gold(("under $300", "HARD"), ("headset for calls", "SOFT")),
        parsed(("headset", "hard"), ("under $300", "hard")),
    )
    assert d.precision == 0.5 and d.recall == 0.5
    assert d.misses == [{"text": "headset for calls", "kind": "SOFT"}]
    assert d.extras == [{"text": "headset", "kind": "hard"}]
    assert d.kind_confusions == [{
        "gold": "headset for calls", "gold_kind": "SOFT",
        "parsed": "headset", "parsed_kind": "hard",
    }]
    assert d.kind_accuracy == 0.5
    assert not d.perfect


def test_an_unmatched_extra_costs_precision_not_recall(runner):
    d = runner.decode_score(
        gold(("16GB", "HARD"), ("cheapest", "SOFT")),
        parsed(("Cheapest", "soft"), ("16GB", "hard"), ("laptop", "hard")),
    )
    assert d.precision == pytest.approx(2 / 3) and d.recall == 1.0
    assert d.extras == [{"text": "laptop", "kind": "hard"}]
    assert d.misses == [] and d.kind_confusions == []
    assert not d.perfect


def test_overlap_below_the_floor_and_not_a_subset_does_not_match(runner):
    # {cheap, light, laptop, bag} vs {light, phone}: Jaccard 1/5, no subset.
    d = runner.decode_score(
        gold(("cheap light laptop bag", "SOFT")), parsed(("light phone", "soft")),
    )
    assert d.matched == 0 and d.precision == 0.0 and d.recall == 0.0
    # No shared token at all: never a match, whatever the kinds.
    d = runner.decode_score(gold(("under $800", "HARD")), parsed(("vacuum", "hard")))
    assert d.matched == 0


def test_greedy_matching_is_one_to_one_and_prefers_the_closer_pair(runner):
    """Two parsed clauses could both absorb one gold clause; the closer one
    takes it and the other is an extra, never a double count."""
    d = runner.decode_score(
        gold(("under $1,200", "HARD")),
        parsed(("laptop under $1,200", "hard"), ("under $1,200", "hard")),
    )
    assert d.matched == 1 and d.recall == 1.0 and d.precision == 0.5
    assert d.pairs[0]["parsed"] == "under $1,200"
    assert d.extras == [{"text": "laptop under $1,200", "kind": "hard"}]


def test_empty_edges_are_defined_not_divided_by_zero(runner):
    both_empty = runner.decode_score([], [])
    assert both_empty.precision == 1.0 and both_empty.recall == 1.0 and both_empty.perfect
    invented = runner.decode_score([], parsed(("laptop", "hard")))
    assert invented.precision == 0.0 and invented.recall == 1.0 and not invented.perfect
    missed_all = runner.decode_score(gold(("laptop", "HARD")), [])
    assert missed_all.precision == 1.0 and missed_all.recall == 0.0 and not missed_all.perfect


# --- all thirty frozen requests ---------------------------------------------


@pytest.fixture(scope="module")
def decodes(runner, requests_) -> dict:
    return {r["id"]: runner.decode_score(r["constraints"], parse(r["utterance"]))
            for r in requests_}


def test_all_thirty_decode_without_raising_and_stay_in_range(decodes):
    assert len(decodes) == 30
    for rid, d in decodes.items():
        assert 0.0 <= d.precision <= 1.0, rid
        assert 0.0 <= d.recall <= 1.0, rid
        assert 0.0 <= d.kind_accuracy <= 1.0, rid
        assert d.matched <= min(len(d.gold), len(d.parsed)), rid
        assert len(d.misses) == len(d.gold) - d.matched, rid
        assert len(d.extras) == len(d.parsed) - d.matched, rid


def test_mean_decode_recall_floor(runner, decodes):
    """A floor, not a target. The brief set 0.80; the measured mean is 0.972.

    If this ever fails, report the true number and lower the floor to it minus
    0.05 with a note in the channel -- do not raise the gold to meet it.
    """
    t = runner.decode_totals(decodes)
    assert t["recall"] >= 0.80, f"mean decode recall fell to {t['recall']:.3f}"


def test_mean_decode_precision_floor(runner, decodes):
    """Measured 0.914 at the time of writing; floor set at that minus 0.05."""
    t = runner.decode_totals(decodes)
    assert t["precision"] >= 0.86, f"mean decode precision fell to {t['precision']:.3f}"


def test_the_two_known_kind_confusions_are_the_only_ones(decodes):
    """R14 and R24 both label a use-case noun phrase SOFT ("headset for calls",
    "work laptop") that the parser decodes as the bare HARD category. Reported,
    not fixed: the parser is another owner's file and the gold is frozen."""
    confused = {rid for rid, d in decodes.items() if d.kind_confusions}
    assert confused == {"R14", "R24"}, confused
    assert all(c["gold_kind"] == "SOFT" and c["parsed_kind"] == "hard"
               for d in decodes.values() for c in d.kind_confusions)


def test_r01_decodes_perfectly(decodes):
    """The demo request. All four gold clauses recovered, right kinds, no extra."""
    assert decodes["R01"].perfect


# --- determinism ------------------------------------------------------------


def test_two_runs_are_identical(runner, requests_):
    first = [runner.decode_score(r["constraints"], parse(r["utterance"])).as_json()
             for r in requests_]
    second = [runner.decode_score(r["constraints"], parse(r["utterance"])).as_json()
              for r in requests_]
    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_the_written_reports_carry_the_same_decode(decodes):
    """`data/eval/reports/<id>.json` has a top-level ``decode`` equal to a fresh
    compute. If the parser changes, re-run `scripts/eval_run.py`; this is the
    pin that says the published number and the code agree."""
    for rid, d in decodes.items():
        report = json.loads((REPORTS / f"{rid}.json").read_text(encoding="utf-8"))
        assert "decode" in report, rid
        assert report["decode"] == d.as_json(), rid
        # Additive only: the keys the dashboard already renders are still there.
        assert {"request_id", "utterance", "constraints", "metrics", "merchants", "control"} <= set(report)
