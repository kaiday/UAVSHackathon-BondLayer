"""Onboarding endpoints -- NGUYEN-7, the JSON behind the Onboarding Console.

Mounted as a router rather than added to ``app/api.py``, which Minh owns. The
React console calls these; nothing here renders HTML.

Everything is a projection of ``CatalogReport``. If a number appears on the
console that is not in this module's output, it was invented somewhere it
should not have been.
"""

from __future__ import annotations

import csv
import io
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from bondlayer.adapters import CatalogReport, CsvCatalogAdapter

router = APIRouter(prefix="/onboard", tags=["onboarding"])

DATA = Path(__file__).resolve().parents[3] / "data"
SEED_CATALOG = DATA / "catalog" / "electronics.csv"
UPLOADS = DATA / "uploads"

#: Seeded reports survive a venue with twenty teams on one wifi. An upload
#: replaces the entry for that merchant; nothing else changes.
_reports: dict[str, CatalogReport] = {}


def _serialise(report: CatalogReport) -> dict:
    """The console's whole payload. Ordered worst-first so the fix list reads
    top-down: a merchant should see what makes listings invisible before they
    see what makes them untidy."""
    order = {"blocker": 0, "degrades_match": 1, "cosmetic": 2, "info": 3}
    diagnostics = sorted(
        report.diagnostics, key=lambda d: (order[d.severity.value], d.row)
    )
    return {
        "merchant": report.merchant,
        "rows_read": report.rows_read,
        "rows_rejected": report.rows_rejected,
        "skus": len(report.skus),
        "readiness": report.readiness,
        "attributes_fixed": report.attributes_fixed,
        "by_severity": report.by_severity,
        "by_rule": report.by_rule,
        "diagnostics": [
            {**asdict(d), "severity": d.severity.value} for d in diagnostics
        ],
    }


def seed() -> None:
    """Load the three merchants from the frozen catalogue at start-up."""
    for merchant in ("voltway", "citycircuit", "northgear"):
        _reports[merchant] = CsvCatalogAdapter(SEED_CATALOG, merchant=merchant).analyse()


@router.get("/report/{merchant}")
def report(merchant: str) -> dict:
    if merchant not in _reports:
        raise HTTPException(404, f"no catalogue loaded for {merchant!r}")
    return _serialise(_reports[merchant])


@router.get("/merchants")
def merchants() -> list[dict]:
    """Enough for the console's merchant switcher and the comparison strip."""
    return [
        {
            "merchant": m,
            "rows_read": r.rows_read,
            "readiness": r.readiness,
            "blockers": r.by_severity["blocker"],
        }
        for m, r in sorted(_reports.items())
    ]


@router.post("/catalog")
async def upload_catalog(merchant: str, file: UploadFile) -> dict:
    """Accept a retailer's own export and report on it.

    Deliberately narrow: one CSV, one merchant, UTF-8, fail loudly. The demo
    runs from seeded state, so this path exists to prove the adoption story,
    not to carry the demo.
    """
    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "catalogue must be UTF-8 encoded")

    header = next(csv.reader(io.StringIO(text)), [])
    missing = {"sku", "merchant", "price", "title", "category"} - set(header)
    if missing:
        raise HTTPException(400, f"missing required columns: {sorted(missing)}")

    UPLOADS.mkdir(parents=True, exist_ok=True)
    path = UPLOADS / f"{merchant}.csv"
    path.write_text(text, encoding="utf-8")

    _reports[merchant] = CsvCatalogAdapter(path, merchant=merchant).analyse()
    return _serialise(_reports[merchant])
