"""Merchant assistance grounded in the selected merchant's actual catalogue report."""

from fastapi import APIRouter, HTTPException
from pydantic import Field

from bondlayer import ai
from bondlayer.ucp import onboard

router = APIRouter(prefix="/onboard", tags=["merchant-assistant"])


class AskRequest(ai.AIModel):
    question: str = Field(min_length=1, max_length=3000)


class ReportAnswer(ai.AIModel):
    answer: str
    diagnostic_ids: list[int]


@router.get("/ai")
def ai_status() -> dict:
    return ai.status()


@router.post("/ai/check")
def check_ai() -> dict:
    _, meta = ai.structured("connection_check", "Reply with Connection verified.", {}, ai.Answer)
    return {**ai.status(), "live_verified": True, "ai": meta}


@router.post("/ask/{merchant}")
def ask(merchant: str, body: AskRequest) -> dict:
    report = onboard.report(merchant)
    if not body.question.strip():
        raise HTTPException(422, "question must not be blank")
    # All totals remain server-derived; cap only the detail sent to the model.
    diagnostics = report["diagnostics"][:100]
    context = {**report, "diagnostics": [dict(d, diagnostic_id=i) for i, d in enumerate(diagnostics)],
               "diagnostics_shown": len(diagnostics), "diagnostics_total": len(report["diagnostics"])}
    result, meta = ai.structured(
        "merchant_assistance",
        "Answer the merchant's question from the supplied current report. Explain concrete next "
        "actions in plain language. Distinguish original-data defects from fields already repaired. "
        "Readiness is a diagnostic score, not sales conversion or percent of usable products. "
        "Do not invent product specifications, benefits or sales results. Cite relevant diagnostic_ids "
        "from this report, or use an empty list for an answer about totals. If evidence is absent, say so.",
        {"question": body.question, "report": context}, ReportAnswer,
    )
    if any(i < 0 or i >= len(diagnostics) for i in result.diagnostic_ids):
        raise ai.AIError("The AI answer cited an unknown diagnostic. Please retry.")
    return {"merchant": merchant, "answer": result.answer,
            "citations": [diagnostics[i] for i in dict.fromkeys(result.diagnostic_ids)],
            "source": f"/onboard/report/{merchant}", "ai": meta}
