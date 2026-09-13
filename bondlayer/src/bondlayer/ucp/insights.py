"""Read-only, merchant-scoped business insights over real local activity."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from bondlayer import activity
from bondlayer.insights import build_insights

router = APIRouter(prefix="/onboard", tags=["shopping-insights"])


@router.get("/insights/{merchant}")
def shopping_insights(
    merchant: str,
    days: int = Query(default=30, ge=0, le=90),
    mode: Literal["enabled", "control", "all"] = Query(default="enabled"),
) -> dict:
    from bondlayer.ucp import server
    if days not in {0, 7, 30, 90}:
        raise HTTPException(422, "days must be 0, 7, 30 or 90")
    profile = server._merchant(merchant)
    return {**build_insights(activity.reports(merchant=merchant), merchant, days=days, mode=mode),
            "display_name": profile.display_name}
