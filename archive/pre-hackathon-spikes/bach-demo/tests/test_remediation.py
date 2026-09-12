"""The corrected export has to be trustworthy, or it is worse than nothing.

A merchant downloads this file and edits it. Two properties make that safe,
and neither is visible by looking at the screen.
"""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bondlayer.ingest import remediation  # noqa: E402
from bondlayer.ingest.catalog_adapter import adapt_csv_text  # noqa: E402

MESSY = """sku,name,brand,price,barcode,waterproofing,weight,sizes,colour,stock
A-1,Alpha Shell,Acme,$249.00,9351234567890,15k mm,520g,"S, M, L",Navy,7
A-2,Beta Wind,Acme,"AUD 139.50",935123456,waterproof-ish,280g,S/M/L,Ochre,3
A-3,Gamma Coat,Acme,POA,,20K mm H2O,1.2kg,"M, L",Charcoal,2
"""


def _run():
    offers, issues = adapt_csv_text(MESSY, "acme", "Acme")
    return offers, issues


def test_a_row_we_could_not_map_still_appears_in_the_download() -> None:
    """Silently dropping it would return a file that looks clean and is short.

    That is the most misleading thing this function could do: the merchant
    would diff row counts, find three became two, and have no idea which
    product left or why.
    """
    offers, _ = _run()
    assert len(offers) == 2, "A-3 has an unparseable price and cannot be an offer"

    rows = list(csv.DictReader(io.StringIO(remediation.fixed_csv(MESSY, offers))))
    assert len(rows) == 3, "every input row must survive into the corrected file"

    gamma = next(r for r in rows if r["sku"] == "A-3")
    assert gamma["bondlayer_status"].startswith(remediation.STATUS_ACTION)
    assert "POA" in gamma["bondlayer_status"]


def test_we_never_invent_a_value_a_human_has_to_supply() -> None:
    """A fabricated GTIN would match the wrong product -- worse than none."""
    offers, _ = _run()
    rows = {r["sku"]: r for r in csv.DictReader(io.StringIO(remediation.fixed_csv(MESSY, offers)))}

    # A-2's barcode is too short to be a GTIN, and A-3 has none at all.
    assert rows["A-2"]["gtin"] == ""
    assert rows["A-3"]["gtin"] == ""
    assert "GTIN" in rows["A-2"]["bondlayer_status"]

    # ...while what *was* unambiguous is normalised without being asked.
    assert rows["A-1"]["price_aud"] == "249.00"
    assert rows["A-1"]["waterproof_rating_mm"] == "15000"
    assert rows["A-3"]["sku"] == "A-3"
    assert rows["A-2"]["weight_grams"] == "280"


def test_every_todo_is_either_the_merchants_job_or_already_done() -> None:
    """The split is the whole point of the screen; nothing may fall between."""
    offers, issues = _run()
    todos = remediation.todos(MESSY, offers, issues)
    assert todos

    for t in todos:
        if t.auto_fixed:
            assert t.severity == "fixed"
        else:
            # Actionable items must name the products and say what it costs.
            assert t.severity != "fixed"
            assert t.products, f"{t.id} gives the merchant no product to act on"
            assert t.impact

    # The unresolved waterproofing row is a job, not a boast.
    water = [t for t in todos if t.field == "waterproofing" and not t.auto_fixed]
    assert water and "Beta Wind" in water[0].products


def test_changed_cells_reflect_what_the_reader_sees() -> None:
    """'S/M/L' becomes 'S|M|L' on screen, so it must be marked as changed."""
    offers, _ = _run()
    changed = remediation.changed_cells(MESSY, offers)
    assert "sizes" in changed["A-2"], "S/M/L -> S|M|L is a visible change"
    assert "sizes" in changed["A-1"]
    assert "price_aud" in changed["A-1"]
