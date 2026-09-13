"""Live policy upload -> OpenAI drafts -> merchant review -> signed publication."""

from dataclasses import asdict
from decimal import Decimal

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field
from pypdf.errors import PdfReadError

from bondlayer.policy import PolicyError
from bondlayer.records.canonical import canonical_record
from bondlayer.ucp import benefits

router = APIRouter(prefix="/onboard/policies", tags=["policy-onboarding"])


class EditDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fact: dict[str, str | int | float] | None = None
    conditions: list[str] | None = None
    value_ceiling_aud: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)


def draft_payload(draft) -> dict:
    payload = jsonable_encoder(asdict(draft))
    payload.pop("confidence", None)  # no invented model confidence score
    return payload


@router.get("/{merchant}")
def policy_state(merchant: str) -> dict:
    from bondlayer.ucp import server
    server._merchant(merchant)
    root = benefits.directory(merchant)
    drafts = []
    if (root / "drafts" / "policy_onboarding.sqlite3").exists():
        drafts = [draft_payload(d) for d in benefits.service(merchant).store.drafts_for(merchant)]
    return {"merchant": merchant, "drafts": drafts, "published_records": server._records.get(merchant, [])}


@router.post("/{merchant}")
def upload_policy(merchant: str, file: UploadFile = File(...)) -> dict:
    onboarding = benefits.service(merchant)
    raw = file.file.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(413, "policy must be 10 MB or smaller")
    try:
        # Extract before replacing the saved document/drafts: a failed model call cannot erase work.
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from bondlayer.policy import PolicyIngestor, PolicyStore
        with TemporaryDirectory() as temporary:
            document = PolicyIngestor(PolicyStore(Path(temporary))).ingest(merchant, file.filename or "policy.txt", raw)
            drafts = onboarding.converter.drafts_for(merchant, document.text)
            with benefits.lock:
                onboarding.store.store_document(merchant, file.filename or "policy.txt", raw, document.text)
                onboarding.store.replace_drafts(merchant, drafts)
        return {**policy_state(merchant), "ai": onboarding.converter.last_call}
    except (PolicyError, ValueError, PdfReadError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.patch("/{merchant}/drafts/{draft_id}")
def edit_draft(merchant: str, draft_id: str, body: EditDraftRequest) -> dict:
    onboarding = benefits.service(merchant)
    try:
        with benefits.lock:
            draft = onboarding.store.get_draft(draft_id)
            if draft.merchant != merchant:
                raise PolicyError("Draft belongs to another merchant")
            # Validate the complete candidate before persisting edits.
            from dataclasses import replace
            values = body.model_dump(exclude_unset=True)
            candidate = replace(draft.record, **values)
            canonical_record(candidate)
            from bondlayer.policy import VALUE_TYPES, DraftStatus
            if draft.status is not DraftStatus.PENDING:
                raise PolicyError("Only pending drafts can be edited")
            if candidate.benefit_type in VALUE_TYPES and candidate.value_ceiling_aud is not None:
                raise PolicyError("Values claims cannot carry a monetary ceiling")
            edited = replace(draft, record=candidate, edited=True)
            onboarding.store.save_draft(edited)
            return draft_payload(edited)
    except (PolicyError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{merchant}/drafts/{draft_id}/{decision}")
def decide(merchant: str, draft_id: str, decision: str) -> dict:
    if decision not in {"approve", "reject"}:
        raise HTTPException(404, "unknown decision")
    onboarding = benefits.service(merchant)
    try:
        with benefits.lock:
            draft = onboarding.store.get_draft(draft_id)
            if draft.merchant != merchant:
                raise PolicyError("Draft belongs to another merchant")
            return draft_payload(getattr(onboarding, decision)(draft_id))
    except (PolicyError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{merchant}/publish")
def publish(merchant: str) -> dict:
    with benefits.lock:
        return benefits.publish(merchant, benefits.service(merchant))
