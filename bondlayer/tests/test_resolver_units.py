"""Two bugs that made whole requests return nothing, held by tests.

Both were found by running the frozen evaluation set through the real catalogue
adapter rather than through hand-built Sku objects. Neither showed up in unit
tests, because both need normalised typed attributes to be visible at all.

Written against WS-A's first resolver; kept as regressions over
``interpret_hard``, which is where round2/dev decodes a HARD clause.
"""

from decimal import Decimal

from bondlayer.interpreter.resolver import interpret_hard


def _kinds(text: str) -> dict[str, object]:
    return {spec.kind: spec.value for spec in interpret_hard(text)}


class TestAComparatorIsNotACurrency:
    """`under 1.3kg` and `under $200` are the same English comparator over
    different quantities. The generic price branch used to claim both, so a
    weight limit was compared against a shelf price and R04 returned nothing.
    """

    def test_a_weight_limit_is_not_a_money_clause(self):
        assert _kinds("under 1.3kg") == {"weight": 1.3}

    def test_a_price_limit_still_is(self):
        assert _kinds("under $200") == {"price": Decimal("200")}
        assert _kinds("under $1,500") == {"price": Decimal("1500")}
        assert _kinds("no more than $2,500") == {"price": Decimal("2500")}

    def test_other_units_are_not_money_either(self):
        for clause in ("16gb", "2tb", "13 inch", "14 inches"):
            assert "price" not in _kinds(clause), clause


class TestCategoryMatchingIsNotSubstringMatching:
    """`phone` is inside `microphone`. Because the ontology was scanned with a
    plain substring test and `phone` came first, every microphone resolved as a
    phone, and R27 -- microphone under $200 -- returned nothing at all.

    This is the exact failure mode the project argues against, reproduced
    inside our own ontology.
    """

    def test_microphone_is_audio_not_phone(self):
        assert _kinds("microphone")["category"] == "audio"

    def test_phone_still_resolves_to_phone(self):
        assert _kinds("phone")["category"] == "phone"

    def test_the_longest_phrase_wins(self):
        # "coffee machine" must beat any shorter fragment inside it
        assert _kinds("coffee machine")["category"] == "appliance"
        assert _kinds("portable ssd")["category"] == "accessory"

    def test_a_word_fragment_does_not_match(self):
        # "dock" must not fire on "docking" or "dockyard"
        assert "category" not in _kinds("dockyard")

    def test_no_category_mentioned_returns_none(self):
        assert "category" not in _kinds("under $200")
