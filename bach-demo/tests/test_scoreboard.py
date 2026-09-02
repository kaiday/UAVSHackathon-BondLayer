"""The scoreboard's two load-bearing claims.

The screen tells a merchant "$X of signed value never reached the agent". Two
things make that a lie if they break, and neither is visible by looking at the
page: the total must exclude value we cannot prove, and a benefit that *did*
reach the agent must not be counted as lost.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bondlayer import scoreboard  # noqa: E402
from bondlayer.agent.policy import CustomerPolicy  # noqa: E402
from bondlayer.demo_data import GOLD_MEMBER, alpine_benefits  # noqa: E402
from bondlayer.schema import Offer  # noqa: E402
from bondlayer.signing import KeyRing, load_or_create_keypair  # noqa: E402

KEYS = Path(__file__).resolve().parents[1] / "data" / "keys"
PRICE = 199.0


def _offers() -> tuple[list[Offer], list[Offer], KeyRing]:
    signer = load_or_create_keypair("alpine", KEYS)
    keyring = KeyRing()
    keyring.pin("alpine", signer.public_key_b64)

    base = dict(
        product_id="ALP-STORM-3L",
        title="Stormline 3L Hardshell Jacket",
        brand="Alpine Outfitters",
        merchant_id="alpine",
        merchant_name="Alpine Outfitters",
        price_aud=PRICE,
        availability="in_stock",
        gtin="9312345678907",
    )
    # The member context travels in the same extension block as the benefits,
    # so the ON offer carries it and the OFF offer cannot. Without it the
    # membership-gated records are ineligible and produce no ledger line at
    # all, which would make this test pass for the wrong reason.
    on = [Offer(**base, benefits=alpine_benefits(signer, PRICE), member=GOLD_MEMBER)]
    off = [Offer(**base, benefits=[])]  # what negotiation actually leaves behind
    return off, on, keyring


def test_recoverable_excludes_unproven_value() -> None:
    """A figure labelled 'recoverable' may only contain signed lines.

    Provisional lines are forecasts. They are listed on the screen so the
    merchant can see them, and deliberately not added to the total -- the same
    ceiling discipline `trv.value_offer` applies to a declared bound.
    """
    off, on, keyring = _offers()
    reasons, recoverable = scoreboard.attribute(on, off, CustomerPolicy(budget_aud=200.0), keyring)

    assert reasons, "the focus merchant should have valued benefits"
    assert any(r.status != "signed" for r in reasons), (
        "this test is only meaningful while at least one line is unproven"
    )
    signed_only = round(sum(r.value_aud for r in reasons if r.status == "signed"), 2)
    assert recoverable == signed_only
    assert recoverable < round(sum(r.value_aud for r in reasons), 2)


def test_a_benefit_that_reached_the_agent_is_not_counted_as_lost() -> None:
    """If the OFF payload already carried a benefit, it was never lost."""
    off, on, keyring = _offers()
    # Hand the "off" condition one of the records, as a partial capability
    # grant would: it is now visible, so it cannot appear in the lost total.
    # A record that actually produces a cost-reducing ledger line -- an
    # ineligible one would be excluded for the wrong reason.
    delivered = next(b for b in on[0].benefits if b.id == "alpine-free-returns")
    off = [off[0].model_copy(update={"benefits": [delivered], "member": GOLD_MEMBER})]

    reasons, recoverable = scoreboard.attribute(on, off, CustomerPolicy(budget_aud=200.0), keyring)
    seen = [r for r in reasons if r.title == delivered.title]
    assert seen and seen[0].reached_agent
    assert delivered.title not in {r.title for r in reasons if not r.reached_agent}

    _, all_lost = scoreboard.attribute(on, _offers()[0], CustomerPolicy(budget_aud=200.0), keyring)
    assert recoverable < all_lost, "delivering a benefit must shrink the lost total"
