"""Fixture-first OpenAI client with provenance.

Every completion is recorded to data/fixtures/ as REAL model output for
the exact prompt that produced it — model, recorded_at, latency — and
replays from there by default, so a stage run never touches the network
and every surface can say exactly what it is showing. The fixture key
hashes the model AND the full prompt: switching model or changing a
payload re-records rather than silently replaying a different
experiment's answer.

  complete(system, user)            replay if recorded, else call + record
  complete(..., live=True)          force a fresh call (re-records)

Needs OPENAI_API_KEY only when a call actually goes out.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "data" / "fixtures"
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5")


def _fixture_path(tag: str, model: str, system: str, user: str) -> Path:
    key = hashlib.sha256(f"{model}\x00{system}\x00{user}".encode()).hexdigest()[:20]
    return FIXTURE_DIR / f"{tag}-{key}.json"


def _call_openai(model: str, system: str, user: str) -> tuple[str, int]:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "No fixture recorded for this prompt and OPENAI_API_KEY is not "
            "set — put the key in .env to record, then runs replay offline.")
    body: dict = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "max_completion_tokens": 2000,
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    t0 = time.time()
    with httpx.Client(timeout=180) as client:
        r = client.post("https://api.openai.com/v1/chat/completions",
                        headers=headers, json=body)
        if r.status_code == 400 and "max_completion_tokens" in r.text:
            body["max_tokens"] = body.pop("max_completion_tokens")
            r = client.post("https://api.openai.com/v1/chat/completions",
                            headers=headers, json=body)
        r.raise_for_status()
    latency_ms = int((time.time() - t0) * 1000)
    return r.json()["choices"][0]["message"]["content"], latency_ms


def complete(system: str, user: str, model: str | None = None,
             tag: str = "llm", live: bool = False) -> dict:
    """Returns {answer, source, model, recorded_at, latency_ms, fixture}.

    source is "fixture" (replayed) or "openai" (fresh call, now recorded).
    """
    model = model or DEFAULT_MODEL
    path = _fixture_path(tag, model, system, user)
    if path.exists() and not live:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["source"] = "fixture"
        data["fixture"] = path.name
        return data

    answer, latency_ms = _call_openai(model, system, user)
    record = {
        "answer": answer,
        "model": model,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "latency_ms": latency_ms,
        # Stored so a fixture is auditable against the prompt that made it.
        "system": system,
        "user_sha256": hashlib.sha256(user.encode()).hexdigest(),
    }
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    record["source"] = "openai"
    record["fixture"] = path.name
    return record
