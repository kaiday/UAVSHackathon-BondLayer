"""Issues -> a to-do list, and a corrected export the merchant can download.

`catalog_adapter` reports what it found. That is a diagnosis, and a diagnosis on
its own is a bill: it tells a merchant they have a problem without telling them
what to do about it. This module closes that gap in the only two ways that
matter to somebody with a job to get back to:

**Do the work that can be done mechanically.** A price written ``AUD 129.00``,
a waterproof rating written ``20K mm H2O``, a weight written ``1.2kg`` and a
size list written ``"S, M, L"`` are all unambiguous. Nobody should be asked to
retype those, so the corrected file carries them already normalised.

**Name the rest as one instruction per fix, not one line per parser event.** A
missing barcode is not a CSV problem, it is "this product cannot be matched
against a competitor's, and only you can supply the number". Ten rows missing a
barcode is *one* to-do with ten products attached, because that is how the work
will actually be done.

The division is deliberate and is the honest part: we never invent a value a
human has to supply. A missing GTIN stays missing and is marked
``ACTION REQUIRED`` in the output, because a fabricated barcode would be far
worse than an absent one -- it would match the wrong product.
"""

from __future__ import annotations

import csv
import io
from dataclasses import asdict, dataclass, field
from typing import Any

from ..schema import Offer
from .catalog_adapter import IngestIssue

#: Columns the corrected export carries, in the order a person reads them.
FIXED_COLUMNS = [
    "sku",
    "name",
    "brand",
    "price_aud",
    "gtin",
    "waterproof_rating_mm",
    "weight_grams",
    "sizes",
    "colour",
    "availability",
    "bondlayer_status",
]

STATUS_OK = "ok"
STATUS_ACTION = "ACTION REQUIRED"


@dataclass
class Todo:
    """One thing a person has to do, with what it costs while undone."""

    id: str
    title: str
    detail: str
    impact: str
    severity: str
    field: str
    rows: list[int] = field(default_factory=list)
    products: list[str] = field(default_factory=list)
    #: True when BondLayer already did this in the corrected file and the
    #: merchant only has to accept it.
    auto_fixed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


#: One entry per kind of problem: the instruction, and the consequence of
#: leaving it. Keyed by (field, whether we could fix it ourselves).
_PLAYBOOK: dict[str, dict[str, str]] = {
    "price": {
        "title": "Give these products a numeric price",
        "detail": (
            "The price cell does not contain a number we can read, so the row "
            "cannot become an offer at all. Values like 'POA' or 'call us' "
            "have no machine-readable equivalent, and guessing one would be "
            "worse than leaving it out."
        ),
        "impact": "These products are invisible to every shopping agent.",
    },
    "barcode": {
        "title": "Add a GTIN barcode to these products",
        "detail": (
            "A GTIN is how an agent knows your product and a competitor's are "
            "the same thing. Without it your listing is compared on title text "
            "if at all. We will not invent one -- a fabricated barcode would "
            "match the wrong product, which is worse than none."
        ),
        "impact": "Agents cannot line these up against a competitor's offer.",
    },
    "waterproofing": {
        "title": "Give these a numeric waterproof rating",
        "detail": (
            "We normalise '10k mm', '20K mm H2O' and '10,000mm' to "
            "millimetres automatically. These rows say something we cannot "
            "turn into a number -- 'waterproof-ish' has no millimetre value, "
            "and inventing one would be a specification claim you never made."
        ),
        "impact": "An agent can display these but cannot compare them.",
    },
}

#: Normalisations the adapter performs silently. They are worth naming, because
#: "we did four things for you" is the answer to "what am I paying for".
_AUTO_NOTES = [
    (
        "price-format",
        "Price formats normalised",
        "Values like 'AUD 129.00' and '$249.00' became plain numbers.",
        "price",
    ),
    (
        "weight",
        "Weights converted to grams",
        "'1.2kg' and '485g' both became a gram figure an agent can sort on.",
        "weight",
    ),
    (
        "sizes",
        "Size lists split",
        "'S, M, L / XL' became a real list rather than one opaque string.",
        "sizes",
    ),
    (
        "waterproofing",
        "Waterproof ratings converted to millimetres",
        "'10k mm', '20K mm H2O' and '10,000mm' all became a plain millimetre "
        "figure, so an agent can compare them numerically.",
        "waterproofing",
    ),
]


def _rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text, newline="")))


def todos(text: str, offers: list[Offer], issues: list[IngestIssue]) -> list[Todo]:
    """Group the adapter's findings into instructions a person can act on."""
    raw = _rows(text)

    def label(row_number: int) -> str:
        """The product a 1-based CSV row refers to, named the way its owner would."""
        idx = row_number - 2  # DictReader rows start at 2 (1 is the header)
        if 0 <= idx < len(raw):
            r = raw[idx]
            return (r.get("name") or r.get("sku") or f"row {row_number}").strip()
        return f"row {row_number}"

    grouped: dict[str, list[IngestIssue]] = {}
    for issue in issues:
        grouped.setdefault(issue.field, []).append(issue)

    out: list[Todo] = []
    for field_name, group in grouped.items():
        play = _PLAYBOOK.get(field_name)
        if play is None:
            play = {
                "title": f"Review the {field_name} column",
                "detail": group[0].problem,
                "impact": group[0].resolution,
            }
        # Everything in `issues` is something the adapter could NOT resolve.
        # An earlier version filed the waterproofing group under "normalised,
        # already applied", which read as a success while pointing at the one
        # row that had failed -- exactly backwards.
        out.append(
            Todo(
                id=f"todo-{field_name}",
                title=play["title"],
                detail=play["detail"],
                impact=play["impact"],
                severity=_severity(field_name),
                field=field_name,
                rows=[i.row for i in group],
                products=sorted({label(i.row) for i in group}),
                auto_fixed=False,
            )
        )

    # Things that went right, stated as done rather than left invisible.
    present = {c.lower() for c in (_rows(text)[0].keys() if raw else [])}
    for tid, title, detail, column in _AUTO_NOTES:
        if column in present:
            out.append(
                Todo(
                    id=f"auto-{tid}",
                    title=title,
                    detail=detail,
                    impact="Already applied in the corrected file.",
                    severity="fixed",
                    field=column,
                    auto_fixed=True,
                )
            )

    # Work the merchant must do first, then what we already handled.
    order = {"invisible": 0, "unmatchable": 1, "incomparable": 2, "fixed": 3}
    out.sort(key=lambda t: (order.get(t.severity, 9), t.title))
    return out


def _severity(field_name: str) -> str:
    if field_name == "price":
        return "invisible"
    if field_name == "barcode":
        return "unmatchable"
    return "incomparable"


def fixed_rows(text: str, offers: list[Offer]) -> list[dict[str, str]]:
    """The corrected export, including the rows that could not be mapped.

    A row we had to skip still appears, marked ``ACTION REQUIRED``. Silently
    dropping it would hand the merchant a file that looks clean and is short --
    the single most misleading thing this function could do.
    """
    by_sku = {o.product_id: o for o in offers}
    out: list[dict[str, str]] = []

    for raw in _rows(text):
        sku = (raw.get("sku") or "").strip()
        offer = by_sku.get(sku)
        if offer is None:
            out.append({
                "sku": sku,
                "name": (raw.get("name") or "").strip(),
                "brand": (raw.get("brand") or "").strip(),
                "price_aud": "",
                "gtin": "",
                "waterproof_rating_mm": "",
                "weight_grams": "",
                "sizes": "",
                "colour": (raw.get("colour") or "").strip(),
                "availability": "",
                "bondlayer_status": (
                    f"{STATUS_ACTION}: price {raw.get('price', '')!r} is not a number"
                ),
            })
            continue

        attrs = offer.attributes
        notes: list[str] = []
        if not offer.gtin:
            notes.append("add a GTIN barcode")
        if "waterproof_rating_mm" not in attrs and raw.get("waterproofing"):
            notes.append("waterproofing not machine-readable")

        out.append({
            "sku": offer.product_id,
            "name": offer.title,
            "brand": offer.brand,
            "price_aud": f"{offer.price_aud:.2f}",
            "gtin": offer.gtin or "",
            "waterproof_rating_mm": str(attrs.get("waterproof_rating_mm", "")),
            "weight_grams": str(attrs.get("weight_grams", "")),
            "sizes": "|".join(attrs.get("sizes", []) or []),
            "colour": str(attrs.get("colour", "")),
            "availability": offer.availability,
            "bondlayer_status": (
                f"{STATUS_ACTION}: " + "; ".join(notes) if notes else STATUS_OK
            ),
        })

    return out


def fixed_csv(text: str, offers: list[Offer]) -> str:
    """`fixed_rows` as a UTF-8 CSV the merchant can open in Excel."""
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=FIXED_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in fixed_rows(text, offers):
        writer.writerow(row)
    return buf.getvalue()


def changed_cells(text: str, offers: list[Offer]) -> dict[str, set[str]]:
    """Which cells differ from the merchant's original, keyed by sku.

    The preview highlights these. Showing a corrected file without saying what
    moved asks the reader to diff two tables by eye.
    """
    by_sku = {o.product_id: o for o in offers}
    out: dict[str, set[str]] = {}
    for raw in _rows(text):
        sku = (raw.get("sku") or "").strip()
        offer = by_sku.get(sku)
        if offer is None:
            continue
        moved: set[str] = set()
        if (raw.get("price") or "").strip() != f"{offer.price_aud:.2f}":
            moved.add("price_aud")
        if raw.get("waterproofing") and "waterproof_rating_mm" in offer.attributes:
            if (raw["waterproofing"] or "").strip() != str(
                offer.attributes["waterproof_rating_mm"]
            ):
                moved.add("waterproof_rating_mm")
        if raw.get("weight") and "weight_grams" in offer.attributes:
            if (raw["weight"] or "").strip() != str(offer.attributes["weight_grams"]):
                moved.add("weight_grams")
        if raw.get("sizes") and offer.attributes.get("sizes"):
            # Compare what the reader sees, not an intermediate. Splitting the
            # raw string and comparing lists said "unchanged" for 'S/M/L',
            # because the split happened to match -- while the cell in front of
            # them had visibly become 'S|M|L'.
            if (raw["sizes"] or "").strip() != "|".join(offer.attributes["sizes"]):
                moved.add("sizes")
        if moved:
            out[sku] = moved
    return out
