"""Two bugs that made whole requests return nothing, held by tests.

Both were found by running the frozen evaluation set through the real catalogue
adapter rather than through hand-built Sku objects. Neither showed up in unit
tests, because both need normalised typed attributes to be visible at all.
"""

from bondlayer.interpreter.resolver import _category_phrase, _is_money_clause


class TestAComparatorIsNotACurrency:
    """`under 1.3kg` and `under $200` are the same English comparator over
    different quantities. The generic price branch used to claim both, so a
    weight limit was compared against a shelf price and R04 returned nothing.
    """

    def test_a_weight_limit_is_not_a_money_clause(self):
        assert _is_money_clause("under 1.3kg") is False

    def test_a_price_limit_still_is(self):
        assert _is_money_clause("under $200") is True
        assert _is_money_clause("under $1,500") is True
        assert _is_money_clause("no more than $2,500") is True

    def test_other_units_are_not_money_either(self):
        for clause in ("16gb", "at least 32gb", "2tb", "13 inch", "14 inches"):
            assert _is_money_clause(clause) is False, clause

    def test_budget_words_are_money_even_without_a_symbol(self):
        assert _is_money_clause("budget around 2000") is True


class TestCategoryMatchingIsNotSubstringMatching:
    """`phone` is inside `microphone`. Because the ontology was scanned with a
    plain substring test and `phone` came first, every microphone resolved as a
    phone, and R27 -- microphone under $200 -- returned nothing at all.

    This is the exact failure mode the project argues against, reproduced
    inside our own ontology.
    """

    def test_microphone_is_audio_not_phone(self):
        assert _category_phrase("microphone") == ("microphone", "audio")

    def test_phone_still_resolves_to_phone(self):
        assert _category_phrase("phone") == ("phone", "phone")

    def test_the_longest_phrase_wins(self):
        # "coffee machine" must beat any shorter fragment inside it
        assert _category_phrase("coffee machine") == ("coffee machine", "appliance")
        assert _category_phrase("portable ssd") == ("portable ssd", "accessory")

    def test_a_word_fragment_does_not_match(self):
        # "dock" must not fire on "docking" or "dockyard"
        assert _category_phrase("dockyard") is None

    def test_no_category_mentioned_returns_none(self):
        assert _category_phrase("under $200") is None
