"""FastAPI adapter for :mod:`bondlayer.onboarding`.

Mount ``create_onboarding_api(Path("var/onboarding.json"))`` behind the
authenticated merchant router; the caller supplies merchant/user identity.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from .onboarding import OnboardingService


class ProfileRequest(BaseModel):
    profile: dict[str, str]
    current_step: str = "profile"


class ConsentRequest(BaseModel):
    user_id: str
    policy_id: str
    version: str


class SubmitRequest(BaseModel):
    user_id: str


def create_onboarding_api(store_path: Path) -> FastAPI:
    service = OnboardingService(store_path)
    app = FastAPI(title="BondLayer onboarding API")

    @app.get("/api/merchants/{merchant_id}/onboarding")
    def get_state(merchant_id: str) -> dict[str, Any]: return service.state(merchant_id)

    @app.put("/api/merchants/{merchant_id}/onboarding/profile")
    def put_profile(merchant_id: str, body: ProfileRequest) -> dict[str, Any]: return service.save_profile(merchant_id, body.profile, body.current_step)

    @app.post("/api/merchants/{merchant_id}/onboarding/uploads")
    async def post_upload(merchant_id: str, document_type: str = Form(...), file: UploadFile = File(...)) -> dict[str, Any]:
        return service.upload(merchant_id, document_type, file.filename or "upload", await file.read())

    @app.post("/api/merchants/{merchant_id}/onboarding/catalogue/import")
    async def post_catalogue(merchant_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
        return service.import_catalogue(merchant_id, file.filename or "catalogue", await file.read())

    @app.get("/api/membership-policy/current")
    def get_membership_policy() -> dict[str, str]: return service.current_membership_policy()

    @app.post("/api/merchants/{merchant_id}/onboarding/membership-consent")
    def post_consent(merchant_id: str, body: ConsentRequest) -> dict[str, Any]:
        try: return service.accept_membership(merchant_id, body.user_id, body.policy_id, body.version)
        except ValueError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/merchants/{merchant_id}/onboarding/submit")
    def post_submit(merchant_id: str, body: SubmitRequest) -> dict[str, Any]: return service.submit(merchant_id, body.user_id)

    return app
