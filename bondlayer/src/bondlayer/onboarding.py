"""Persistent, server-authoritative merchant onboarding state.

The service deliberately stores uploaded bytes separately from the browser and
keeps append-only audit events.  It does not publish catalogue data.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REQUIRED_POLICIES = ("shipping", "returns", "privacy")
REQUIRED_CATALOGUE_FIELDS = ("sku", "name", "price")
STEPS = ("welcome", "profile", "files", "data", "catalogue", "policies", "membership", "review")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _normalise_columns(headers: list[str]) -> dict[str, str]:
    aliases = {"sku": "sku", "product_sku": "sku", "name": "name", "title": "name",
               "price": "price", "price_aud": "price", "sale_price": "price"}
    return {aliases[h.strip().lower()]: h for h in headers if h.strip().lower() in aliases}


class OnboardingService:
    """JSON-backed repository; replaceable with a database repository later."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db: dict[str, Any] = json.loads(path.read_text()) if path.exists() else {"merchants": {}, "audits": []}

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.db, indent=2, sort_keys=True))

    def _merchant(self, merchant_id: str) -> dict[str, Any]:
        return self.db["merchants"].setdefault(merchant_id, {"profile": {}, "current_step": "welcome", "draft_status": "draft", "uploads": [], "policies": {}, "catalogue": None, "consents": [], "submissions": [], "last_saved_at": _now()})

    def _audit(self, merchant_id: str, event: str, detail: dict[str, Any]) -> None:
        self.db["audits"].append({"id": str(uuid.uuid4()), "merchant_id": merchant_id, "event": event, "at": _now(), **detail})

    def save_profile(self, merchant_id: str, profile: dict[str, str], current_step: str = "profile") -> dict[str, Any]:
        m = self._merchant(merchant_id); m["profile"] = {k: v.strip() for k, v in profile.items() if isinstance(v, str)}; m["current_step"] = current_step; m["last_saved_at"] = _now(); self._audit(merchant_id, "profile_saved", {}); self._save(); return self.state(merchant_id)

    def upload(self, merchant_id: str, document_type: str, filename: str, content: bytes) -> dict[str, Any]:
        m = self._merchant(merchant_id); file_id = str(uuid.uuid4()); status = "accepted"; message = None
        allowed = {"business_document": {".pdf", ".png", ".jpg", ".jpeg"}, "catalogue": {".csv", ".xlsx"}, **{p: {".pdf", ".txt", ".md"} for p in REQUIRED_POLICIES}, "terms": {".pdf", ".txt", ".md"}}
        suffix = Path(filename).suffix.lower()
        if document_type not in allowed or suffix not in allowed[document_type]: status, message = "rejected", "Unsupported document type or file extension."
        elif not content: status, message = "rejected", "The uploaded file is empty."
        elif len(content) > 25 * 1024 * 1024: status, message = "rejected", "File exceeds the 25 MB limit."
        record = {"file_id": file_id, "filename": filename, "document_type": document_type, "state": status, "validation_message": message, "uploaded_at": _now(), "sha256": hashlib.sha256(content).hexdigest()}
        m["uploads"].append(record); self._audit(merchant_id, "upload_" + status, {"file_id": file_id, "document_type": document_type}); m["last_saved_at"] = _now()
        if status == "accepted" and document_type in REQUIRED_POLICIES + ("terms",): m["policies"][document_type] = {"file_id": file_id, "filename": filename, "updated_at": _now(), "completed": True}
        self._save(); return record

    def import_catalogue(self, merchant_id: str, filename: str, content: bytes) -> dict[str, Any]:
        upload = self.upload(merchant_id, "catalogue", filename, content)
        if upload["state"] != "accepted": return self._catalogue_result(merchant_id, upload, [], {}, list(REQUIRED_CATALOGUE_FIELDS), [])
        if filename.lower().endswith(".xlsx"):
            upload["state"] = "rejected"; upload["validation_message"] = "XLSX import requires the configured spreadsheet adapter."; self._save(); return self._catalogue_result(merchant_id, upload, [], {}, list(REQUIRED_CATALOGUE_FIELDS), [])
        try:
            rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
            mapping = _normalise_columns(list(rows[0]) if rows else [])
        except (UnicodeDecodeError, csv.Error) as exc:
            upload["state"] = "rejected"; upload["validation_message"] = f"Could not read CSV: {exc}"; self._save(); return self._catalogue_result(merchant_id, upload, [], {}, list(REQUIRED_CATALOGUE_FIELDS), [])
        missing = [f for f in REQUIRED_CATALOGUE_FIELDS if f not in mapping]; errors = []
        valid = 0
        for number, row in enumerate(rows, start=2):
            fields = [f for f in REQUIRED_CATALOGUE_FIELDS if not (row.get(mapping.get(f, "")) or "").strip()]
            if fields: errors.append({"row": number, "fields": fields, "message": "Required value missing.", "destination_step": "catalogue"})
            else: valid += 1
        result = self._catalogue_result(merchant_id, upload, rows, mapping, missing, errors); self._merchant(merchant_id)["catalogue"] = result; self._audit(merchant_id, "catalogue_imported", {"file_id": upload["file_id"], "valid": valid, "rejected": len(errors)}); self._save(); return result

    def _catalogue_result(self, merchant_id: str, upload: dict[str, Any], rows: list[dict[str, str]], mapping: dict[str, str], missing: list[str], errors: list[dict[str, Any]]) -> dict[str, Any]:
        return {"file_id": upload["file_id"], "state": upload["state"], "validation_message": upload["validation_message"], "total_imported_products": len(rows), "valid_products": len(rows) - len(errors) if not missing else 0, "rejected_products": len(errors) if not missing else len(rows), "mapped_fields": mapping, "missing_required_fields": missing, "row_errors": errors, "error_report_url": None, "issue_destination_step": "data" if missing else "catalogue"}

    def current_membership_policy(self) -> dict[str, str]:
        return {"policy_id": "bondlayer-merchant-membership", "version": "1.0", "content_reference": "/policies/merchant-membership/1.0"}

    def accept_membership(self, merchant_id: str, user_id: str, policy_id: str, version: str) -> dict[str, Any]:
        policy = self.current_membership_policy()
        if (policy_id, version) != (policy["policy_id"], policy["version"]): raise ValueError("The membership policy has changed; retrieve and accept the current version.")
        record = {**policy, "merchant_id": merchant_id, "accepting_user_id": user_id, "accepted_at": _now(), "acknowledged": True}; self._merchant(merchant_id)["consents"].append(record); self._audit(merchant_id, "membership_accepted", {"version": version, "user_id": user_id}); self._save(); return record

    def state(self, merchant_id: str) -> dict[str, Any]:
        m = self._merchant(merchant_id); incomplete = []
        if not all(m["profile"].get(k) for k in ("business_name", "registration", "contact")): incomplete.append({"code": "business_profile", "destination_step": "profile"})
        if not any(x["document_type"] == "business_document" and x["state"] == "accepted" for x in m["uploads"]): incomplete.append({"code": "business_document", "destination_step": "files"})
        c = m["catalogue"]
        if not c or c["state"] != "accepted" or c["valid_products"] == 0: incomplete.append({"code": "catalogue", "destination_step": "catalogue"})
        for p in REQUIRED_POLICIES:
            if not m["policies"].get(p, {}).get("completed"): incomplete.append({"code": f"{p}_policy", "destination_step": "policies"})
        policy = self.current_membership_policy()
        if not any(x["policy_id"] == policy["policy_id"] and x["version"] == policy["version"] for x in m["consents"]): incomplete.append({"code": "membership_consent", "destination_step": "membership"})
        completed = [s for s in STEPS if not any(x["destination_step"] == s for x in incomplete)]
        return {"merchant_id": merchant_id, "current_step": m["current_step"], "completed_steps": completed, "draft_status": m["draft_status"], "submitted": bool(m["submissions"]), "last_saved_at": m["last_saved_at"], "incomplete_requirements": incomplete, "uploads": m["uploads"], "policies": {"required_categories": list(REQUIRED_POLICIES), "items": m["policies"]}, "membership_policy": policy}

    def submit(self, merchant_id: str, user_id: str) -> dict[str, Any]:
        state = self.state(merchant_id)
        if state["incomplete_requirements"]: return {"accepted": False, "status": "blocked", "incomplete_requirements": state["incomplete_requirements"]}
        entry = {"submission_id": str(uuid.uuid4()), "submitted_at": _now(), "submitted_by": user_id, "status": "submitted"}; m = self._merchant(merchant_id); m["submissions"].append(entry); m["draft_status"] = "submitted"; self._audit(merchant_id, "onboarding_submitted", entry); self._save(); return {"accepted": True, **entry}
