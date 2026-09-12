"""FastAPI routes for policy-document onboarding."""

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
from typing import Callable

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel

from bondlayer.policy import PolicyError, PolicyOnboardingService


class EditDraftRequest(BaseModel):
    fact: dict[str, str | int | float] | None = None
    conditions: list[str] | None = None
    value_ceiling_aud: Decimal | None = None


class DecisionRequest(BaseModel):
    note: str | None = None


def create_policy_router(service: PolicyOnboardingService) -> APIRouter:
    router = APIRouter(prefix="/onboard", tags=["policy-onboarding"])

    @router.post("/policy")
    def upload_policy(
        merchant: str = Query(min_length=1),
        filename: str = Query(min_length=1),
        content: bytes = Body(),
    ) -> dict:
        return _call(lambda: asdict(service.ingest_and_draft(merchant, filename, content)))

    @router.get("/report/{merchant}")
    def policy_report(merchant: str) -> dict:
        return _call(lambda: asdict(service.report(merchant)))

    @router.patch("/records/{draft_id}")
    def edit_draft(draft_id: str, request: EditDraftRequest) -> dict:
        return _call(lambda: _draft_response(service.edit(draft_id, **request.model_dump())))

    @router.post("/records/{draft_id}/approve")
    def approve_draft(draft_id: str, request: DecisionRequest) -> dict:
        return _call(lambda: _draft_response(service.approve(draft_id, request.note)))

    @router.post("/records/{draft_id}/reject")
    def reject_draft(draft_id: str, request: DecisionRequest) -> dict:
        return _call(lambda: _draft_response(service.reject(draft_id, request.note)))

    @router.post("/publish/{merchant}")
    def publish(merchant: str) -> list[dict]:
        return _call(lambda: [_signed_response(signed) for signed in service.publish(merchant)])

    return router


def _call(action: Callable):
    try:
        return action()
    except PolicyError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


def _draft_response(draft) -> dict:
    response = asdict(draft)
    response["status"] = draft.status.value
    if draft.signed:
        response["signed"] = _signed_response(draft.signed)
    return response


def _signed_response(signed) -> dict:
    return {"record": asdict(signed.record), "signature": signed.signature, "key_id": signed.key_id}
