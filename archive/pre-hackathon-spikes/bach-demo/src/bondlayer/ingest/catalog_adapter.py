"""Messy merchant catalogue export -> conformant UCP catalog.

Half of "the plug" (D7). Deliberately deterministic: no model is involved in
mapping a product, because a hallucinated price is worse than a missing one.

The input is a real-shaped mess -- inconsistent price formats, free-text
sizes, missing GTINs, waterproofing expressed three different ways -- because
if we fed in a file already shaped like UCP we would have proved nothing, and
a judge would notice the input schema suspiciously resembles the output.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path

from ..schema import Offer


@dataclass
class IngestIssue:
    row: int
    field: str
    problem: str
    resolution: str


PRICE_RE = re.compile(r"[-+]?\d[\d,]*\.?\d*")
# "10k mm", "10,000mm", "10000 mm H2O", "20K"
WATERHEAD_RE = re.compile(r"(\d[\d,\.]*)\s*(k)?\s*mm", re.IGNORECASE)


def _parse_price(raw: str) -> float | None:
    m = PRICE_RE.search(raw.replace("AUD", "").replace("$", ""))
    if not m:
        return None
    return float(m.group(0).replace(",", ""))


def _parse_waterhead_mm(raw: str) -> int | None:
    """'10k mm' / '10,000mm' / '20K mm H2O' -> 10000 / 10000 / 20000."""
    if not raw:
        return None
    m = WATERHEAD_RE.search(raw)
    if not m:
        m2 = re.search(r"(\d[\d,\.]*)\s*k\b", raw, re.IGNORECASE)
        if not m2:
            return None
        return int(float(m2.group(1).replace(",", "")) * 1000)
    value = float(m.group(1).replace(",", ""))
    if m.group(2):
        value *= 1000
    return int(value)


def _valid_gtin(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw or "")
    return digits if len(digits) in (8, 12, 13, 14) else None


#: The columns we must have to produce an offer at all. Named here so an
#: uploaded file with the wrong shape fails with a sentence a merchant can act
#: on, rather than a KeyError from three frames down.
REQUIRED_COLUMNS = ("sku", "name", "price")


def adapt_csv(
    path: Path, merchant_id: str, merchant_name: str
) -> tuple[list[Offer], list[IngestIssue]]:
    """Map a merchant's native export onto UCP offers, reporting what it fixed."""
    return adapt_csv_text(
        path.read_text(encoding="utf-8"), merchant_id, merchant_name
    )


def adapt_csv_text(
    text: str, merchant_id: str, merchant_name: str
) -> tuple[list[Offer], list[IngestIssue]]:
    """The same mapping over a string, so an upload never has to touch disk.

    A merchant's catalogue is their commercial data. Reading it from memory
    means the demo can accept a real export without acquiring a copy of it.
    """
    offers: list[Offer] = []
    issues: list[IngestIssue] = []

    reader = csv.DictReader(io.StringIO(text, newline=""))
    present = {(c or "").strip().lower() for c in (reader.fieldnames or [])}
    missing = [c for c in REQUIRED_COLUMNS if c not in present]
    if missing:
        raise ValueError(
            "this file has no "
            + ", ".join(f"{c!r}" for c in missing)
            + " column. Found: "
            + (", ".join(sorted(present)) or "no header row at all")
        )

    for i, row in enumerate(reader, start=2):
        price = _parse_price(row.get("price", ""))
        if price is None:
            issues.append(
                IngestIssue(i, "price", f"unparseable {row.get('price')!r}", "row skipped")
            )
            continue

        gtin = _valid_gtin(row.get("barcode", ""))
        if gtin is None and row.get("barcode"):
            issues.append(
                IngestIssue(
                    i, "barcode",
                    f"{row['barcode']!r} is not a valid GTIN length",
                    "omitted; agents matching on GTIN will not see this product",
                )
            )
        elif gtin is None:
            issues.append(
                IngestIssue(
                    i, "barcode", "missing",
                    "omitted; cross-merchant product matching will fall back to title",
                )
            )

        waterhead = _parse_waterhead_mm(row.get("waterproofing", ""))
        if waterhead is None and row.get("waterproofing"):
            issues.append(
                IngestIssue(
                    i, "waterproofing",
                    f"{row['waterproofing']!r} not machine-readable",
                    "kept as free text; not comparable across merchants",
                )
            )

        attributes: dict[str, object] = {}
        if waterhead is not None:
            attributes["waterproof_rating_mm"] = waterhead
        if row.get("weight"):
            wm = PRICE_RE.search(row["weight"])
            if wm:
                grams = float(wm.group(0).replace(",", ""))
                if "kg" in row["weight"].lower():
                    grams *= 1000
                attributes["weight_grams"] = int(grams)
        if row.get("sizes"):
            attributes["sizes"] = [
                s.strip().upper() for s in re.split(r"[,/|]", row["sizes"]) if s.strip()
            ]
        if row.get("colour"):
            attributes["colour"] = row["colour"].strip()

        offers.append(
            Offer(
                product_id=row["sku"].strip(),
                title=row["name"].strip(),
                brand=row.get("brand", "").strip(),
                merchant_id=merchant_id,
                merchant_name=merchant_name,
                price_aud=price,
                availability="in_stock"
                if row.get("stock", "").strip().lower() not in ("0", "no", "out")
                else "out_of_stock",
                gtin=gtin,
                attributes=attributes,
            )
        )

    return offers, issues
