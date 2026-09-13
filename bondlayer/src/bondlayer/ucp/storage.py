"""Uploaded merchant data. No bundled catalogue is loaded by default."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from uuid import uuid4

from bondlayer.adapters import CatalogReport, CsvCatalogAdapter
from bondlayer.ucp.profile import DATA, Merchant

UPLOADS = Path(os.environ.get("BONDLAYER_UPLOADS_DIR", str(DATA / "uploads")))
MERCHANT_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
logger = logging.getLogger(__name__)


def test_data_enabled() -> bool:
    """An explicit opt-in used by historical regression tests, never the launcher."""
    return os.environ.get("BONDLAYER_TEST_DATA") == "1"


def validate_id(merchant_id: str) -> str:
    if not MERCHANT_ID.fullmatch(merchant_id):
        raise ValueError("merchant id must be 1–64 lowercase letters, numbers, hyphens or underscores")
    return merchant_id


def uploaded_merchant(merchant_id: str, *, display_name: str = "", domain: str = "") -> Merchant:
    validate_id(merchant_id)
    return Merchant(
        id=merchant_id, display_name=display_name or merchant_id.replace("-", " ").replace("_", " ").title(),
        domain=domain, role="retailer", publishes_benefit_extension=False, signs_records=False,
    )


def load_uploads(root: Path) -> list[tuple[Merchant, CatalogReport]]:
    """Load saved profiles plus legacy CSV uploads, preserving existing user data."""
    loaded = {}
    for path in sorted(root.glob("*.merchant.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            merchant = uploaded_merchant(**payload["profile"])
            if path.name != f"{merchant.id}.merchant.json":
                raise ValueError("merchant id does not match saved filename")
            report = CsvCatalogAdapter(None, merchant.id, text=payload["catalogue"]).analyse()
            if not report.skus:
                raise ValueError("catalogue contains no usable products")
            loaded[merchant.id] = (merchant, report)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            logger.warning("Skipping invalid merchant upload %s: %s", path.name, exc)
    for path in sorted(root.glob("*.csv")):
        if path.stem in loaded:
            continue
        try:
            merchant = uploaded_merchant(path.stem)
            report = CsvCatalogAdapter(path, merchant.id, strict_columns=False).analyse()
            if not report.skus:
                raise ValueError("catalogue contains no usable products")
            loaded[merchant.id] = (merchant, report)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            logger.warning("Skipping invalid catalogue %s: %s", path.name, exc)
    return list(loaded.values())


def save_upload(root: Path, merchant: Merchant, text: str) -> None:
    """Commit profile and catalogue in one atomic file replacement."""
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{validate_id(merchant.id)}.merchant.json"
    temporary = root / f".{merchant.id}.{uuid4().hex}.tmp"
    payload = {
        "profile": {"merchant_id": merchant.id, "display_name": merchant.display_name, "domain": merchant.domain},
        "catalogue": text,
    }
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
