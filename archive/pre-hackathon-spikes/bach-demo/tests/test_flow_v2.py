"""The v2 flow's claims, as tests (docs/demo-flow-v2.md).

Two things the redesign added must not be allowed to quietly become false:

  * the information-gap metrics are DERIVED from the payload the agent actually
    received, so they cannot drift away from what the model saw;
  * a repeat with no fixture is REPORTED, never counted as a model vote.

The second is the one that matters. `run_llm_agent` falls back to list-price
ranking when no model answers, and that fallback names a winner. Tallying it
would manufacture unanimity out of a machine that has no fixtures at all.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))  # app.api, for the state-leak test

from bondlayer import visibility  # noqa: E402
from bondlayer.demo_data import build_services  # noqa: E402
from bondlayer.agent import repeat as rp  # noqa: E402
from bondlayer.agent.repeat import RepeatTally, RepeatVote  # noqa: E402
from bondlayer.agent.trv import LedgerLine, Valuation  # noqa: E402
from bondlayer.schema import Offer  # noqa: E402
from bondlayer.signing import KeyRing  # noqa: E402


def _offer(mid: str, price: float, benefits=()) -> Offer:
    o = Offer(
        merchant_id=mid,
        merchant_name=mid.title(),
        product_id=f"{mid}-1",
        gtin="9312345678907",
        title="Stormline 3L Hardshell Jacket",
        brand="Alpine Outfitters",
        price_aud=price,
    )
    o.benefits = list(benefits)
    return o


# ----------------------------------------------------------------------
# visibility
# ----------------------------------------------------------------------

def test_claims_counted_from_the_payload_not_from_the_offer():
    """The metric reads the JSON the model was handed.

    If someone adds a field to `_offer_for_model` the number moves on its own;
    if someone adds one to `Offer` but never publishes it, it does not.
    """
    payload = json.dumps(
        {
            "offers": [
                {
                    "merchant_id": "alpine",
                    "list_price_aud": 199.0,
                    "attributes": {"waterproof_rating_mm": 20000, "sizes": ["S", "M"]},
                }
            ]
        }
    )
    vis = visibility.measure(
        payload, [_offer("alpine", 199.0)], KeyRing(), benefits_published=6
    )
    # merchant_id + list_price_aud + waterproof_rating_mm + sizes(one claim)
    assert vis.fields_visible == 4


def test_a_scalar_list_is_one_claim_not_five():
    """"Sizes S-XL" is a single thing the agent can reason about. Counting it
    as five would inflate the headline metric for free, which is exactly the
    kind of number this demo exists to refuse."""
    assert visibility._count_claims({"sizes": ["XS", "S", "M", "L", "XL"]}) == 1


def test_withheld_benefits_are_the_gap_between_published_and_delivered():
    payload = json.dumps({"offers": [{"merchant_id": "alpine"}]})
    vis = visibility.measure(
        payload, [_offer("alpine", 199.0)], KeyRing(), benefits_published=6
    )
    assert (vis.benefits_delivered, vis.benefits_withheld) == (0, 6)
    assert vis.offer_legible_pct == 0.0


def test_only_signed_lines_count_as_verified_value():
    """A provisional line is a forecast and an unverified one is never valued.
    Neither belongs in a number labelled "verified value the agent can credit"."""
    offer = _offer("alpine", 199.0)
    val = Valuation(
        offer=offer,
        list_price_aud=199.0,
        lines=[
            LedgerLine(label="member price", amount_aud=-9.95, status="signed", basis=""),
            LedgerLine(label="tier progress", amount_aud=-2.00, status="provisional", basis=""),
            LedgerLine(label="unsigned claim", amount_aud=+4.00, status="unverified", basis=""),
        ],
    )
    vis = visibility.measure(
        json.dumps({"offers": [{"merchant_id": "alpine"}]}),
        [offer],
        KeyRing(),
        benefits_published=6,
        valuations=[val],
    )
    assert vis.verified_value_aud == 9.95


# ----------------------------------------------------------------------
# repeats
# ----------------------------------------------------------------------

def test_orderings_are_distinct_and_stable():
    orders = rp.orderings(3, 5)
    assert len(orders) == len(set(orders)) == 5
    assert orders == rp.orderings(3, 5)  # stable across calls, so fixtures hold


def test_a_fallback_is_reported_not_counted():
    """The failure this test exists for: a machine with no fixtures would
    otherwise report a confident 5/5 for whoever is cheapest."""
    tally = RepeatTally(
        votes=[RepeatVote((0, 1, 2), None, False, "", "not recorded") for _ in range(5)]
    )
    assert tally.n_recorded == 0
    assert tally.counts == {}
    assert tally.headline() == "0 runs recorded"
    assert not tally.unanimous


def test_a_split_vote_is_never_rounded():
    votes = [RepeatVote((0, 1, 2), "alpine", True, "", "fx") for _ in range(3)]
    votes += [RepeatVote((1, 0, 2), "peak", True, "", "fx") for _ in range(2)]
    tally = RepeatTally(votes=votes)
    assert tally.headline() == "3/5 alpine"
    assert not tally.unanimous
    assert tally.counts == {"alpine": 3, "peak": 2}


def test_unrecorded_runs_are_excluded_from_the_denominator():
    votes = [RepeatVote((0, 1, 2), "alpine", True, "", "fx") for _ in range(4)]
    votes.append(RepeatVote((2, 1, 0), None, False, "", "not recorded"))
    tally = RepeatTally(votes=votes)
    assert tally.headline() == "4/4 alpine"
    assert tally.as_dict()["n_attempted"] == 5
    assert tally.unanimous


# ----------------------------------------------------------------------
# live chat
# ----------------------------------------------------------------------

def test_verdict_line_is_stripped_from_what_the_shopper_reads():
    """The model is asked for a machine-readable last line so the console never
    has to guess a winner from prose. The shopper must never see it."""
    from bondlayer.agent import chat as ch

    visible, winner = ch.strip_verdict(
        "Alpine is the better buy once returns are counted.\nRECOMMENDATION: alpine"
    )
    assert winner == "alpine"
    assert "RECOMMENDATION" not in visible
    assert visible == "Alpine is the better buy once returns are counted."


def test_a_reply_with_no_verdict_line_still_renders():
    from bondlayer.agent import chat as ch

    visible, winner = ch.strip_verdict("I'd need your size first.")
    assert winner is None
    assert visible == "I'd need your size first."


def test_chat_prompt_never_mentions_the_extension():
    """D8: the agent has no BondLayer code and no knowledge of the schema. If
    the prompt ever names it, the demo is telling the model the answer."""
    from bondlayer.agent import chat as ch

    lowered = ch.CHAT_SYSTEM.lower()
    for word in ("bondlayer", "benefit_value", "org.bondlayer", "extension"):
        assert word not in lowered, f"chat prompt leaks {word!r}"


def test_grounding_is_a_user_turn_not_a_system_instruction():
    """The catalog is data the agent fetched, not configuration it was given.
    Putting it in the system prompt would misrepresent that in the transcript."""
    from bondlayer.agent import chat as ch
    from bondlayer.signing import KeyRing as _KR

    ctx = ch.build_context([_offer("alpine", 199.0)], _KR(), True)
    assert ctx.payload.lstrip().startswith("{")
    assert "over UCP" in ch._grounding(ctx)


def test_ledger_toggles_do_not_leak_into_the_rest_of_the_demo() -> None:
    """The publish levers and adversary toggles must not mutate global state.

    Both work by reconfiguring the live merchant services, because querying
    them over real HTTP is the whole point. That makes the change global, and
    without the restore an unticked lever on the merchant console would
    silently strip those benefits from the chat and the scoreboard as well --
    the money shot would answer a question nobody asked, and it would look
    like a model result rather than a leaked toggle.
    """
    import app.api as api

    api.SERVICES.setdefault("alpine", None)
    if api.SERVICES.get("alpine") is None:
        services, _ = build_services()
        api.SERVICES.update(services)

    before_alpine = {k: list(v) for k, v in api.SERVICES["alpine"].benefits.items()}
    before_ridgeway = {k: list(v) for k, v in api.SERVICES["ridgeway"].benefits.items()}

    with api._reconfigured(tampered=True, inflate=1000.0, publish=""):
        stripped = api.SERVICES["alpine"].benefits
        assert all(not recs for recs in stripped.values()), (
            "the context manager should have applied the filter"
        )

    assert {k: list(v) for k, v in api.SERVICES["alpine"].benefits.items()} == before_alpine
    assert {
        k: list(v) for k, v in api.SERVICES["ridgeway"].benefits.items()
    } == before_ridgeway
