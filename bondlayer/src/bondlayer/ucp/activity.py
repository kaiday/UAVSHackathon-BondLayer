"""Internal report ingestion for local processes and independently deployed Fly apps."""

import os
import secrets
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from bondlayer import activity

router = APIRouter(prefix="/internal", tags=["service-activity"])


class MerchantObservation(BaseModel):
    model_config = ConfigDict(extra="allow")
    merchant: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    won: bool
    control_merchant: bool


class ObservedReport(BaseModel):
    model_config = ConfigDict(extra="allow")
    request_id: str = Field(pattern=r"^live-[a-f0-9]{32}$")
    source: Literal["live"]
    created_at: AwareDatetime
    utterance: str = Field(min_length=1, max_length=4000)
    merchants: list[MerchantObservation] = Field(min_length=1)
    constraints: list[dict]
    control: list[MerchantObservation] = Field(default_factory=list)


def authorize(request: Request) -> None:
    expected = os.environ.get("BONDLAYER_SERVICE_TOKEN", "")
    if expected:
        supplied = request.headers.get("X-BondLayer-Service-Token", "")
        if not secrets.compare_digest(supplied.encode(), expected.encode()):
            raise HTTPException(401, "invalid service token")
    elif (
        os.environ.get("FLY_APP_NAME")
        or os.environ.get("BONDLAYER_REQUIRE_SERVICE_TOKEN") == "1"
        or request.client is None
        or request.client.host not in {"127.0.0.1", "::1"}
    ):
        raise HTTPException(503, "Configure BONDLAYER_SERVICE_TOKEN on both services before sending request reports.")


@router.post("/requests")
async def receive_report(request: Request) -> dict:
    authorize(request)
    from bondlayer.ucp import server

    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 2 * 1024 * 1024:
            raise HTTPException(413, "request report must be 2 MB or smaller")
        chunks.append(chunk)
    try:
        report = ObservedReport.model_validate_json(b"".join(chunks)).model_dump(mode="json")
    except ValidationError as exc:
        raise HTTPException(422, "invalid observed request report") from exc
    if any(row["merchant"] not in server._merchants for row in report["merchants"]):
        raise HTTPException(422, "request report names an unknown merchant")
    try:
        request_id = activity.persist_report(report)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(503, "request report could not be saved; retry with the same request id") from exc
    return {"request_id": request_id, "saved": True}
