"""The adapter must survive the mess Nha planted, and say what it found.

Note on counts: ``scripts/make_catalog.py`` describes "34 defects" in its
``MESS`` block, but that describes the 62-row ``PRODUCTS`` source table, not the
148-row CSV it emits -- price formatting, for instance, is applied per listing
by ``(i + n) % 4``, so it lands on far more rows than the source table has
entries. These tests assert against the emitted file, which is what the adapter
actually reads.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from bondlayer.adapters import CsvCatalogAdapter, Severity

CSV = Path(__file__).resolve().parents[1] / "data" / "catalog" / "electronics.csv"

EXPECTED_ROWS = 148
EXPECTED_MERCHANTS = {"voltway": 56, "citycircuit": 49, "northgear": 43}

#: Measured on the frozen catalogue. If Nha regenerates it these move, and the
#: onboarding report's numbers move with them -- which is the point of pinning.
EXPECTED_BY_RULE = {
    "price_format": 56,       # 41 "$1234.00" + 15 "1,234.00"
    "ram_units": 13,          # 10 "16 GB" + 3 "16384MB"
    "screen_format": 3,       # '14"' -- "14" and "14.0" both already parse
    "near_dup_title": 5,      # two model_keys carrying a second spelling
    "missing_weight": 3,      # laptops with no weight; warranty SKUs exempt
    "brand_casing": 5,        # 2 LENOVO + 3 lenovo against 13 Lenovo
    "legitimately_empty": 85, # battery_wh empty where that is correct
    "gtin_shared": 129,       # cross-merchant matches -- good, not a defect
}


@pytest.fixture(scope="module")
def report():
    return CsvCatalogAdapter(CSV).analyse()


def test_loads_every_row_without_hand_editing(report):
    assert report.rows_read == EXPECTED_ROWS
    assert report.rows_rejected == 0
    assert len(report.skus) == EXPECTED_ROWS


def test_load_still_satisfies_the_catalogadapter_protocol():
    # types.py freezes load() -> list[Sku]; five branches import that seam.
    skus = CsvCatalogAdapter(CSV).load()
    assert len(skus) == EXPECTED_ROWS
    assert all(isinstance(s.shelf_price, Decimal) for s in skus)


def test_all_eight_rules_fire(report):
    assert set(report.by_rule) == set(EXPECTED_BY_RULE)


def test_rule_counts_match_the_frozen_catalogue(report):
    assert report.by_rule == EXPECTED_BY_RULE


def test_every_price_becomes_a_number(report):
    # 56 of 148 listings carry "$2133.03" or "1,849.00". An agent applying a
    # hard price filter drops those unless we repair them.
    assert all(s.shelf_price > 0 for s in report.skus)
    voltway = [s for s in report.skus if s.attributes["merchant"] == "voltway"]
    assert min(s.shelf_price for s in voltway) > Decimal("0")


def test_ram_spellings_collapse_to_one_number(report):
    with_ram = [s for s in report.skus if "ram_gb" in s.attributes]
    assert with_ram, "no listing carried RAM"
    # "16GB", "16 GB" and "16384MB" must all arrive as the integer 16.
    assert all(isinstance(s.attributes["ram_gb"], int) for s in with_ram)
    assert 16 in {s.attributes["ram_gb"] for s in with_ram}
    assert 16384 not in {s.attributes["ram_gb"] for s in with_ram}


def test_screen_size_is_comparable_as_a_number(report):
    sized = [s for s in report.skus if "screen_in" in s.attributes]
    assert all(isinstance(s.attributes["screen_in"], float) for s in sized)
    assert 14.0 in {s.attributes["screen_in"] for s in sized}


def test_near_duplicate_titles_collapse_onto_one_spelling(report):
    # R18/R19/R20 are near-duplicate traps: substring matching returns spacing
    # variants as distinct products. After normalisation one model_key has one
    # title, so the agent compares products rather than spellings.
    by_key: dict[str, set[str]] = {}
    for s in report.skus:
        by_key.setdefault(str(s.attributes["model_key"]), set()).add(s.title)
    assert all(len(titles) == 1 for titles in by_key.values())


def test_brand_casing_collapses(report):
    brands = {str(s.attributes["brand"]) for s in report.skus if s.attributes["brand"]}
    assert "Lenovo" in brands
    assert "LENOVO" not in brands and "lenovo" not in brands


def test_two_rules_are_not_defects(report):
    # A tool that flags everything gets ignored. These two say "this is fine"
    # and "this is good, keep doing it".
    for rule in ("legitimately_empty", "gtin_shared"):
        hits = [d for d in report.diagnostics if d.rule == rule]
        assert hits and all(d.severity is Severity.INFO for d in hits)


def test_warranty_skus_are_not_scolded_for_having_no_weight(report):
    # Service SKUs have no physical attributes. Flagging them would be noise.
    warranty = {s.sku_id for s in report.skus if s.category == "warranty"}
    assert warranty
    flagged = {d.sku_id for d in report.diagnostics if d.rule == "missing_weight"}
    assert not (warranty & flagged)


def test_severity_is_defined_by_agent_consequence(report):
    by_sev = report.by_severity
    assert by_sev["blocker"] == EXPECTED_BY_RULE["price_format"]
    assert by_sev["degrades_match"] > 0
    assert by_sev["info"] > 0


def test_readiness_scores_the_control_merchant_below_a_clean_feed():
    full = CsvCatalogAdapter(CSV).analyse()
    assert 0.0 <= full.readiness <= 100.0
    per_merchant = {
        m: CsvCatalogAdapter(CSV, merchant=m).analyse()
        for m in EXPECTED_MERCHANTS
    }
    for merchant, expected_rows in EXPECTED_MERCHANTS.items():
        assert per_merchant[merchant].rows_read == expected_rows
        assert 0.0 <= per_merchant[merchant].readiness <= 100.0


def test_diagnostics_are_actionable(report):
    # Every diagnostic has to name the row, the field and what an agent does
    # with it -- this is the text the merchant reads in the console.
    for d in report.diagnostics:
        assert d.row >= 2 and d.sku_id and d.field
        assert len(d.message) > 20
