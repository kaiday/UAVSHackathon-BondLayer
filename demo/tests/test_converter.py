"""Converter guardrails — tested against invented and faithful inputs
directly (the team spike's lesson: a test that asserts what the model
produced is testing the recording, not the check)."""

from agentbridge import loyalty
from agentbridge.converter import approve_and_sign, quote_appears

DOC = ("All enrolled members pay **10% below the listed price** on every "
       "order, storewide, capped at **$20.00** of discount per order.\n"
       "A **free upgrade to express shipping** — normally a **$9.95** "
       "surcharge at checkout.")


def test_quote_survives_markdown_emphasis():
    """The D9.15 failure mode: the document writes **$9.95**, the model
    faithfully quotes $9.95 — that must MATCH, not reject."""
    assert quote_appears("normally a $9.95 surcharge at checkout", DOC)
    assert quote_appears("capped at $20.00 of discount per order", DOC)


def test_quote_survives_whitespace_and_case():
    assert quote_appears("ALL ENROLLED  members pay 10% below\nthe listed price", DOC)


def test_invented_sentence_is_rejected():
    assert not quote_appears("members receive a $100 welcome voucher", DOC)
    assert not quote_appears("", DOC)


def test_approved_draft_signs_and_verifies():
    card = approve_and_sign({
        "benefit_type": "member_price",
        "description": "Members pay 10% below list, capped at $20.00/order.",
        "conditions": "Any enrolled member.",
        "min_tier": "BRONZE",
        "category": None,
        "facts": {"percent_off": 10.0},
        "value_ceiling_cents": 2000,
        "source_quote": "capped at $20.00 of discount per order",
    }, index=1)
    assert loyalty.verify_card(card)
    quote = loyalty.value_cards(loyalty.find_member("ava@example.com"),
                                4200, "electronics", cards=[card])
    assert quote.price_credit_cents == 420  # same arithmetic as the built-in card
