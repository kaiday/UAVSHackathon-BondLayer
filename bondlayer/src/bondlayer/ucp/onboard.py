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
from threading import Lock
from urllib.parse import urlsplit

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from bondlayer.adapters import CatalogReport, CsvCatalogAdapter
from bondlayer.ucp.storage import UPLOADS, save_upload, test_data_enabled, uploaded_merchant, validate_id

router = APIRouter(prefix="/onboard", tags=["onboarding"])

DATA = Path(__file__).resolve().parents[3] / "data"
SEED_CATALOG = DATA / "catalog" / "electronics.csv"
REPORTS = DATA / "eval" / "reports"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_publish_lock = Lock()

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
    """Reports come from the same uploads the server restored."""
    _seed_requests()


def _seed_requests() -> None:
    """Load the frozen-request reports WS-A's eval runner already wrote.

    Read at start-up, from disk, verbatim -- this dashboard renders the
    ``RequestReport`` shape, it never derives it.
    """
    _requests.clear()
    if not test_data_enabled() or not REPORTS.is_dir():
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
    from bondlayer.ucp import server

    return [
        {
            "merchant": m,
            "display_name": server._merchants[m].display_name,
            "domain": server._merchants[m].domain,
            "rows_read": r.rows_read,
            "readiness": r.readiness,
            "blockers": r.by_severity["blocker"],
        }
        for m, r in sorted(_reports.items())
    ]


@router.get("/catalog/template")
def catalogue_template() -> Response:
    """A header-only template: users supply their own products and prices."""
    return Response(
        "sku,title,category,price,currency,brand,stock,ram,storage,weight_kg\r\n",
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="catalogue-template.csv"'},
    )


@router.post("/catalog")
async def upload_catalog(
    merchant: str | None = None, file: UploadFile = File(...),
    display_name: str | None = Form(default=None), domain: str | None = Form(default=None),
    preview: bool = False, create: bool = False,
) -> dict:
    """Validate first, then atomically persist and publish a real catalogue.

    ``preview`` computes the same readiness report without creating a merchant.
    ``create`` prevents onboarding from overwriting an existing merchant.
    A merchant column is optional when the caller supplies ``?merchant=``.
    """
    from bondlayer.ucp import server

    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "catalogue must be 10 MB or smaller")
    try:
        text = raw.decode("utf-8-sig")
        if merchant is None:
            rows = list(csv.DictReader(io.StringIO(text)))
            file_merchants = {(row.get("merchant") or "").strip() for row in rows}
            if len(file_merchants) != 1 or not next(iter(file_merchants), ""):
                raise ValueError("include exactly one merchant in the CSV or provide ?merchant=")
            merchant = file_merchants.pop()
        validate_id(merchant)
        analysed = CsvCatalogAdapter(None, merchant=merchant, text=text).analyse()
        if not analysed.skus:
            raise ValueError("catalogue has no usable products for this merchant")
        if display_name is not None and not 1 <= len(display_name.strip()) <= 120:
            raise ValueError("business name must be 1–120 characters")
        if domain:
            parsed = urlsplit(domain if "://" in domain else "https://" + domain)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or "." not in parsed.hostname:
                raise ValueError("website must be a valid HTTP(S) domain")
            domain = parsed.hostname.lower()
    except (UnicodeError, ValueError, KeyError, csv.Error) as exc:
        raise HTTPException(400, f"catalogue could not be analysed: {exc}") from exc

    with _publish_lock:
        existing = server._merchants.get(merchant)
        if create and existing is not None:
            raise HTTPException(409, "merchant already exists; replace its catalogue from the Catalogue page")
        profile = uploaded_merchant(
            merchant,
            display_name=display_name.strip() if display_name is not None else (existing.display_name if existing else ""),
            domain=domain if domain is not None else (existing.domain if existing else ""),
        )
        if not preview:
            try:
                save_upload(server.UPLOADS, profile, text)
            except OSError as exc:
                raise HTTPException(500, "could not save catalogue; please retry") from exc
            server._catalog[merchant] = analysed.skus
            server._records[merchant] = []
            _reports[merchant] = analysed
            server._merchants[merchant] = profile
    return {"merchant": merchant, "display_name": profile.display_name,
            "report": _serialise(analysed), "published": not preview}


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
    """No fabricated history on a new installation."""
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
