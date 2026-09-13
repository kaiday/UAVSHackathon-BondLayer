"""Build observed request reports; the merchant owns their persistent storage."""

import json
import re
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from bondlayer.ucp.storage import UPLOADS
from bondlayer.insights import capture_observation

_write_lock = Lock()


def build_report(run, merchants: list[str], snapshots: dict, ai: dict, order: dict) -> dict:
    """Pure report construction, safe to run in a stateless buyer-agent container."""
    request_id = f"live-{uuid4().hex}"
    rows = []
    for merchant in merchants:
        offer = next((r for r in run.ranked if r.merchant == merchant), None)
        product = next((p for p in snapshots.get(merchant, {}).get("products", []) if offer and p["id"] == offer.sku_id), None)
        won = bool(offer is not None and run.winner is offer)
        rows.append({
            "merchant": merchant, "control_merchant": False, "won": won,
            "observation": capture_observation(run, merchant, snapshots.get(merchant, {}), order),
            "fields_exposed": len(product.get("attributes", {})) + len([key for key in product if key != "attributes"]) if product else 0,
            "legible_share": sum(r.satisfied for r in offer.resolved) / len(run.constraints) if offer and run.constraints else 0,
            "value_credited_aud": str(offer.credited) if offer else None,
            "value_withheld_aud": None,
            "sku_id": offer.sku_id if offer else None,
            "shelf_price": str(offer.shelf_price) if offer else None,
            "effective_cost": str(offer.effective_cost) if offer else None,
            "unsatisfied": [c.text for c in offer.unsatisfied] if offer else [c["text"] for c in run.constraints],
            "lost_because": None if won else (
                "No matching product was returned for this merchant." if offer is None else
                "Another merchant ranked ahead in the model's comparison."
                if ai.get("ranking", {}).get("provider") == "openai" else "Another merchant ranked ahead under this request's deterministic comparison."
            ),
        })
    return {
        "request_id": request_id, "utterance": run.utterance, "source": "live",
        "created_at": datetime.now(timezone.utc).isoformat(), "extension_enabled": run.extension_enabled,
        "bundle": bool(run.bundles), "expect_unsatisfied": False,
        "constraints": run.constraints, "metrics": {}, "unsatisfied": run.unsatisfied,
        "bundle_composed": None, "merchants": rows, "control": [], "ai": ai, "order": order,
    }


def persist_report(report: dict) -> str:
    """Atomic, idempotent merchant-side persistence; IDs cannot become file paths."""
    request_id = report.get("request_id", "")
    if not isinstance(request_id, str) or not re.fullmatch(r"live-[a-f0-9]{32}", request_id):
        raise ValueError("invalid request report id")
    payload = json.dumps(report, ensure_ascii=False, default=str, allow_nan=False)
    with _write_lock:
        root = UPLOADS / "requests"
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{request_id}.json"
        if path.exists():
            if json.loads(path.read_text(encoding="utf-8")) != json.loads(payload):
                raise ValueError("request report id is already used by a different report")
            return request_id
        temporary = root / f".{request_id}.{uuid4().hex}.tmp"
        try:
            temporary.write_text(payload, encoding="utf-8")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return request_id


def save_request(run, merchants: list[str], snapshots: dict, ai: dict, order: dict) -> str:
    """Compatibility helper for local scripts/tests; the running agent submits over HTTP."""
    return persist_report(build_report(run, merchants, snapshots, ai, order))


def reports(merchant: str | None = None) -> dict[str, dict]:
    """Retain up to 500 reports after merchant filtering, not before it."""
    out = {}
    for path in sorted((UPLOADS / "requests").glob("live-*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            if merchant is not None and not any(row.get("merchant") == merchant for row in report.get("merchants", [])):
                continue
            out[report["request_id"]] = report
            if len(out) >= 500:
                break
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
    return out
