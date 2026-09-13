"""Buyer model calls through the shared OpenAI service, with per-request evidence."""

from __future__ import annotations

import json
import time
from contextvars import ContextVar
from typing import Literal

from bondlayer import ai
from bondlayer.agent.trace import AgentRun


class RankedOffer(ai.AIModel):
    rank: int
    merchant: str
    sku_id: str
    decisive_terms: list[str]
    reasoning: str


class Ranking(ai.AIModel):
    ranking: list[RankedOffer]
    recommendation: str


class ChatDecision(ai.AIModel):
    action: Literal["search", "reply"]
    utterance: str | None
    reply: str | None


_transcript: ContextVar[tuple[dict, ...]] = ContextVar("buyer_transcript", default=())


def reset_transcript() -> None:
    _transcript.set(())


def _complete(label: str, system: str, data: object, schema):
    started = time.monotonic()
    result, meta = ai.structured(label, system, data, schema)
    call = {
        **meta, "label": label, "system": system,
        "prompt": data if isinstance(data, str) else json.dumps(data, ensure_ascii=False),
        "completion": result.model_dump_json(),
        "latency_ms": int((time.monotonic() - started) * 1000),
    }
    _transcript.set((*_transcript.get(), call))
    return result, meta


def complete_json(label: str, system: str, prompt: str) -> dict:
    schema = {"rank": Ranking, "route": ChatDecision}[label]
    result, meta = _complete(label, system, prompt, schema)
    return {**result.model_dump(), "ai": meta}


def chat(label: str, system: str, messages: list[dict[str, str]]) -> str:
    result, _ = _complete(label, system, messages, ai.Answer)
    return result.answer


def transcript_payload() -> list[dict]:
    return list(_transcript.get())


def narrate(run: AgentRun) -> dict:
    """Explain the reference comparison when explicit offline mode is selected."""
    if ai.mode() == "rules":
        winner = run.winner
        text = (
            f"{winner.merchant}'s {winner.title} ({winner.sku_id}) ranks first with a "
            f"shelf price of ${winner.shelf_price:.2f}, credited benefit value of "
            f"${winner.credited:.2f}, and effective comparison cost of ${winner.effective_cost:.2f}. "
            "This explanation is generated in explicit offline rules mode."
            if winner else "No merchant returned a matching, priced listing for this request."
        )
        return {"text": text, "source": "template", "note": "Explicit rules mode; no OpenAI call."}
    result, meta = _complete(
        "recommendation",
        "Explain this already-computed shopping comparison. Do not change the winner. "
        "Effective cost is indicative value, not the checkout amount.",
        {"request": run.utterance, "offers": [
            {"merchant": r.merchant, "sku": r.sku_id, "title": r.title,
             "shelf_price": str(r.shelf_price), "effective_cost": str(r.effective_cost),
             "citations": r.citations, "unsatisfied": [c.text for c in r.unsatisfied]}
            for r in run.ranked[:10]
        ]}, ai.Answer,
    )
    return {"text": result.answer, "source": "model",
            "note": f"OpenAI: {meta['model']} ({meta['response_id']})", "ai": meta}
