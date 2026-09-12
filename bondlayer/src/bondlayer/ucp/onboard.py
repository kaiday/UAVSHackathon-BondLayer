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
import json
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from bondlayer.adapters import CatalogReport, CsvCatalogAdapter

router = APIRouter(prefix="/onboard", tags=["onboarding"])

DATA = Path(__file__).resolve().parents[3] / "data"
SEED_CATALOG = DATA / "catalog" / "electronics.csv"
UPLOADS = DATA / "uploads"
REPORTS = DATA / "eval" / "reports"

#: Seeded reports survive a venue with twenty teams on one wifi. An upload
#: replaces the entry for that merchant; nothing else changes.
_reports: dict[str, CatalogReport] = {}

#: The 30 frozen-request reports WS-A's eval runner writes to
#: ``data/eval/reports/<id>.json`` -- read once, from disk, at start-up. This
#: module only serves them; it computes nothing.
_requests: dict[str, dict] = {}


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
    _seed_requests()


def _seed_requests() -> None:
    """Load the frozen-request reports WS-A's eval runner already wrote.

    Read at start-up, from disk, verbatim -- this dashboard renders the
    ``RequestReport`` shape, it never derives it.
    """
    _requests.clear()
    if not REPORTS.is_dir():
        return
    for path in sorted(REPORTS.glob("*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        _requests[report["request_id"]] = report


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


# --- "why we lost": the per-request console (WS-E) --------------------------


def _request_summary(report: dict) -> dict:
    """One row for the Requests list -- enough to pick a request, nothing
    more. The four figures live on the detail route, not here."""
    return {
        "request_id": report["request_id"],
        "utterance": report["utterance"],
        "merchants": [
            {
                "merchant": m["merchant"],
                "control_merchant": m["control_merchant"],
                "won": m["won"],
            }
            for m in report["merchants"]
        ],
    }


@router.get("/requests")
def requests_list() -> list[dict]:
    """The 30 frozen requests, for the dashboard's request picker."""
    return [_request_summary(r) for _, r in sorted(_requests.items())]


@router.get("/requests/{request_id}")
def request_detail(request_id: str, merchant: str | None = None) -> dict:
    """The ``RequestReport`` JSON for one request, straight off disk.

    Without ``merchant``: the whole report -- every merchant's row, three-way,
    control included. With ``merchant``: just that merchant's row, so the
    dashboard can ask for exactly the row it is about to render.
    """
    if request_id not in _requests:
        raise HTTPException(404, f"no report for request {request_id!r}")
    report = _requests[request_id]
    if merchant is None:
        return report
    for row in report["merchants"]:
        if row["merchant"] == merchant:
            return {
                "request_id": report["request_id"],
                "utterance": report["utterance"],
                **row,
            }
    raise HTTPException(
        404, f"no merchant {merchant!r} on request {request_id!r}"
    )
