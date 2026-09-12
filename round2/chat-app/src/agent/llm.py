"""Model client: live on every call, temperature 0, with a visible transcript.

Every call is live. There is no fixture replay -- a decision taken knowingly
(see issue #11, D8): the stage result is decided in the room, and the framing is
that the agent decides and we do not rig it.

Temperature 0 is a reproducibility default, not a hedge. It is not a
determinism guarantee across a live API.

Whatever the model answers is appended to TRANSCRIPT with its prompt, its
verbatim completion and its provenance, and mirrored to ``data/transcript.jsonl``.
A demo that shows only a parsed winner is asking to be taken on trust.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path(__file__).resolve().parents[2] / "data"
TRANSCRIPT_PATH = DATA / "transcript.jsonl"

DEFAULT_MODEL = os.environ.get("BONDLAYER_MODEL", "gpt-4o-mini")


@dataclass
class Call:
    """One model call, as it happened."""

    label: str
    model: str
    system: str
    prompt: str
    completion: str
    latency_ms: int
    at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


#: Every call this process has made, newest last. The UI renders it.
TRANSCRIPT: list[Call] = []


class LLMUnavailable(RuntimeError):
    """Raised when no usable provider is configured."""


def _client():
    key = os.environ.get("OPENAI_API_KEY")
    if not key or key.startswith("sk-your"):
        raise LLMUnavailable(
            "OPENAI_API_KEY is missing or still the placeholder. "
            "Put a real key in round2/chat-app/.env"
        )
    from openai import OpenAI

    return OpenAI(api_key=key)


def complete(label: str, system: str, prompt: str, *, as_json: bool = False) -> str:
    """One live completion. Returns the verbatim text."""
    client = _client()
    kwargs: dict[str, Any] = {
        "model": DEFAULT_MODEL,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    }
    if as_json:
        kwargs["response_format"] = {"type": "json_object"}

    started = time.monotonic()
    response = client.chat.completions.create(**kwargs)
    latency_ms = int((time.monotonic() - started) * 1000)
    text = response.choices[0].message.content or ""

    call = Call(
        label=label,
        model=DEFAULT_MODEL,
        system=system,
        prompt=prompt,
        completion=text,
        latency_ms=latency_ms,
    )
    TRANSCRIPT.append(call)
    _append(call)
    return text


def complete_json(label: str, system: str, prompt: str) -> Any:
    """A completion parsed as JSON, or ``None`` when the model did not comply.

    The caller decides what an unparseable answer means. Silently substituting
    an empty result would hide a failed run behind a plausible-looking ranking.
    """
    text = complete(label, system, prompt, as_json=True)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
        return None


def _append(call: Call) -> None:
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        with TRANSCRIPT_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(call), ensure_ascii=False) + "\n")
    except OSError:
        # A transcript we cannot write is not a reason to fail the run.
        pass


def transcript_payload() -> list[dict]:
    return [asdict(c) for c in TRANSCRIPT]
