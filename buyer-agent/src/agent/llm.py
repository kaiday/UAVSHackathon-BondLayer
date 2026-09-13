"""Optional prose over an already-decided ranking. Never on the ranking path.

D4 (Ford, 12/09): ranking is deterministic, always -- ``run_request``'s
effective-cost arithmetic, full stop. The model, when a key is configured,
writes one paragraph explaining what the trace already shows. It never sees
the offers before the ranking exists, and it cannot change the winner: there
is no code path from this module back into ``composition.run_request``.

No key -> a template sentence, built from the same ``AgentRun``, and a note
saying so. This module **never raises** on a missing key: a shopper closing a
non-negotiation venue's wifi should still get a ranked, credited answer with a
plain-English sentence attached, not a 500.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bondlayer.agent.trace import AgentRun

DATA = Path(__file__).resolve().parents[2] / "data"
TRANSCRIPT_PATH = DATA / "transcript.jsonl"

#: Named for what it is: an OpenAI chat model, used for prose only. There is
#: no Anthropic key anywhere on this path, and no ranking dependency on it
#: either way.
DEFAULT_MODEL = os.environ.get("BONDLAYER_MODEL", "gpt-4o-mini")


@dataclass
class Call:
    label: str
    model: str
    prompt: str
    completion: str
    latency_ms: int
    at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


#: Every call this process has made, newest last. The UI renders it.
TRANSCRIPT: list[Call] = []


def _has_key() -> bool:
    key = os.environ.get("OPENAI_API_KEY")
    return bool(key) and not key.startswith("sk-your")


def _template(run: AgentRun) -> str:
    """A deterministic sentence built from the trace -- always available."""
    winner = run.winner
    if winner is None:
        return "No merchant returned a matching, priced listing for this request."
    cheapest = min(run.ranked, key=lambda r: r.shelf_price)
    if winner.sku_id == cheapest.sku_id:
        return (
            f"{winner.merchant}'s {winner.title} ({winner.sku_id}) wins on shelf price "
            f"alone at ${winner.shelf_price:.2f}; no merchant's verified benefits changed "
            f"the ranking here."
        )
    return (
        f"{winner.merchant}'s {winner.title} ({winner.sku_id}) costs ${winner.shelf_price:.2f} "
        f"on the shelf, ${winner.credited:.2f} more than {cheapest.merchant}'s cheapest "
        f"listing, but {winner.records_verified} verified benefit(s) bring its effective "
        f"cost to ${winner.effective_cost:.2f} -- below {cheapest.merchant}'s "
        f"${cheapest.shelf_price:.2f}. That is the flip: a signed, verifiable offer beating "
        f"the cheapest shelf price once what it actually includes is counted."
    )


def _append(call: Call) -> None:
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        with TRANSCRIPT_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(call), ensure_ascii=False) + "\n")
    except OSError:
        # A transcript we cannot write is not a reason to fail the run.
        pass


def _complete(prompt: str) -> str:
    """One live completion. Raises on any failure; the caller decides what a
    failure means (it never propagates past :func:`narrate`)."""
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    started = time.monotonic()
    response = client.chat.completions.create(
        model=DEFAULT_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": (
                "You write one short, neutral paragraph explaining a shopping "
                "comparison that has already been decided by deterministic "
                "arithmetic. State the winner, the shelf price, the credited "
                "value and why. Never suggest a different winner -- the "
                "ranking is not yours to make."
            )},
            {"role": "user", "content": prompt},
        ],
    )
    latency_ms = int((time.monotonic() - started) * 1000)
    text = (response.choices[0].message.content or "").strip()
    TRANSCRIPT.append(Call("narrate", DEFAULT_MODEL, prompt, text, latency_ms))
    _append(TRANSCRIPT[-1])
    return text


def narrate(run: AgentRun) -> dict[str, Any]:
    """One paragraph of prose over an already-ranked run. Never raises.

    Returns ``{"text", "source", "note"}`` -- ``source`` is ``"model"`` or
    ``"template"``, and ``note`` is the sentence the trace shows for this
    step, e.g. ``"prose: template (no model key)"``.
    """
    template_text = _template(run)
    if not _has_key():
        return {"text": template_text, "source": "template",
                 "note": "prose: template (no model key)"}

    prompt = (
        f'The customer asked: "{run.utterance}"\n\n'
        f"Deterministic trace:\n"
        + "\n".join(f"- [{s.phase.value}:{s.outcome.value}] {s.summary}" for s in run.steps)
        + "\n\nRanked offers (already decided, do not re-rank):\n"
        + "\n".join(
            f"- #{i} {r.merchant} {r.sku_id} shelf=${r.shelf_price:.2f} "
            f"credited=${r.credited:.2f} effective=${r.effective_cost:.2f}"
            for i, r in enumerate(run.ranked, start=1)
        )
    )
    try:
        text = _complete(prompt)
        if not isinstance(text, str) or not text:
            raise ValueError("empty completion")
        return {"text": text, "source": "model", "note": f"prose: {DEFAULT_MODEL}"}
    except Exception as exc:  # noqa: BLE001 - any failure here falls back, never raises
        return {"text": template_text, "source": "template",
                 "note": f"prose: template (model call failed: {type(exc).__name__})"}


def transcript_payload() -> list[dict]:
    return [asdict(c) for c in TRANSCRIPT]
