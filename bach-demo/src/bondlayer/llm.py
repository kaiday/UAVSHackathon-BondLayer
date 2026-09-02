"""Model client, fixture-first, with a visible transcript (D9.10, D9.13).

Every call is keyed by a hash of (model, system, prompt) and cached to
data/fixtures/. If a fixture exists it is returned without touching the
network. If not, a live transport records one.

Two reasons this is fixture-first rather than fixture-fallback:

  - Stage safety. The pinned baseline run of D5 falls out for free: once the
    baseline has been recorded, it replays byte-identically every time, so the
    "before" cannot accidentally pick our merchant on stage.
  - The demo must run on a laptop with no API key and no wifi.

Three live transports (D9.13), preferred in this order:

  openai      the OpenAI SDK, when OPENAI_API_KEY is set.
  anthropic   the Anthropic SDK, when ANTHROPIC_API_KEY is set.
  claude_cli  `claude -p`, when the Claude Code CLI is installed and logged
              in -- an OAuth session instead of a key. This exists because it
              is what removed the "hand-authored fixtures" caveat that used to
              sit at the top of the README, on a machine with no key at all.

Nothing above the transport layer knows or cares which provider answered: the
agent's prompts contain no provider-specific instructions, and D8 already
requires the published catalog data to be legible to a model that has never
seen our schema. Being able to swap the provider and re-record is the cheapest
way to test that claim -- see DECISIONS.md D9.16.

`BONDLAYER_LLM` forces a transport (`openai`, `anthropic`, `claude_cli`, or
`off` for fixtures only). `BONDLAYER_MODEL` overrides the model id.

Whichever answered, the call is appended to TRANSCRIPT with its prompt, its
verbatim completion and its provenance, so the UI and the terminal can show
what the model was actually asked and what it actually said. A demo that shows
only a parsed winner_merchant_id is asking to be taken on trust.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: Default model per transport. Override either with BONDLAYER_MODEL.
DEFAULT_MODELS = {
    "openai": "gpt-5",
    "anthropic": "claude-sonnet-5",
    "claude_cli": "claude-sonnet-5",
}

#: Enough completion budget that a reasoning model can think and still answer.
REASONING_HEADROOM_TOKENS = 8000
#: The point at which we stop doubling and admit the prompt is the problem.
REASONING_CEILING_TOKENS = 32000

#: Model families that bill thinking against the completion budget. Matched by
#: prefix rather than an exact list, so a point release does not silently fall
#: back to a budget that cannot answer.
_REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def _is_reasoning_model(model: str) -> bool:
    return any(model.startswith(p) for p in _REASONING_PREFIXES)


#: Kept as a module constant because the fixture key hashes the model id, so
#: anything computing a key outside a call needs the same answer this does.
MODEL = DEFAULT_MODELS["anthropic"]

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "data" / "fixtures"

#: Human-readable provenance. `authored` means a person wrote the completion
#: by hand; it is never evidence of model behaviour. "api" is the old name for
#: "anthropic" and is still read so fixtures recorded before the OpenAI
#: transport existed keep their provenance.
SOURCE_LABELS = {
    "authored": "HAND-AUTHORED - not model output",
    "openai": "recorded live - OpenAI API",
    "anthropic": "recorded live - Anthropic API",
    "api": "recorded live - Anthropic API",
    "claude_cli": "recorded live - claude CLI",
    "fallback": "no model available - deterministic fallback",
    "unknown": "unknown provenance",
}

#: Sources that mean "a real model produced this".
RECORDED_SOURCES = ("openai", "anthropic", "api", "claude_cli")


class LLMUnavailable(RuntimeError):
    """No fixture and no live transport -- the caller must fall back."""


# ----------------------------------------------------------------------
# Transcript
# ----------------------------------------------------------------------

@dataclass
class CallRecord:
    """One model call, as it happened. Everything the audience should see."""

    label: str
    model: str
    system: str
    prompt: str
    completion: str
    source: str                 # openai | anthropic | claude_cli | authored | fallback
    served_from: str            # fixture | live | none
    fixture: str | None = None
    recorded_at: str | None = None
    latency_ms: int | None = None
    usage: dict[str, Any] = field(default_factory=dict)

    @property
    def provenance(self) -> str:
        return SOURCE_LABELS.get(self.source, self.source)

    @property
    def is_real(self) -> bool:
        return self.source in RECORDED_SOURCES


TRANSCRIPT: list[CallRecord] = []


def reset_transcript() -> None:
    TRANSCRIPT.clear()


def transcript_for(label: str) -> list[CallRecord]:
    return [c for c in TRANSCRIPT if c.label == label]


def last_call(label: str) -> CallRecord | None:
    calls = transcript_for(label)
    return calls[-1] if calls else None


def fixture_provenance() -> dict[str, int]:
    """How many fixtures on disk are real recordings vs hand-authored.

    Always carries a `recorded` total, so callers do not have to know the list
    of transports to ask the only question that matters: is what I am about to
    show a real model or a person typing what they wished a model had said.
    """
    counts = {
        "openai": 0, "anthropic": 0, "api": 0, "claude_cli": 0,
        "authored": 0, "unknown": 0, "for_current_model": 0, "empty": 0,
    }
    wanted = default_model()
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            counts["unknown"] += 1
            continue
        source = blob.get("source")
        if source not in counts:
            source = "authored" if blob.get("authored") else "unknown"
        counts[source] += 1
        empty = not (blob.get("completion") or "").strip()
        if empty:
            # Surfaced separately: an empty fixture is unusable, and a banner
            # reporting it among the "recorded live" total is lying.
            counts["empty"] += 1
        if blob.get("model") == wanted and not empty:
            counts["for_current_model"] += 1
    counts["recorded"] = sum(counts[s] for s in RECORDED_SOURCES)
    counts["model"] = wanted
    return counts


# ----------------------------------------------------------------------
# Transports
# ----------------------------------------------------------------------

def _key(system: str, prompt: str, model: str) -> str:
    h = hashlib.sha256()
    h.update(model.encode())
    h.update(b"\x00")
    h.update(system.encode())
    h.update(b"\x00")
    h.update(prompt.encode())
    return h.hexdigest()[:20]


def _claude_cli() -> str | None:
    return os.environ.get("CLAUDE_CLI") or shutil.which("claude")


def configured_transport() -> str | None:
    """Which transport the environment asks for, ignoring availability.

    Separate from available_transport() because the fixture key hashes the
    model id: the model has to be resolved before we know whether a fixture
    will serve the call, and a run with BONDLAYER_LLM=off must still look up
    the same key it would have recorded under.
    """
    forced = os.environ.get("BONDLAYER_LLM", "auto").lower()
    if forced in ("openai", "anthropic", "claude_cli"):
        return forced
    if forced == "api":  # old name, kept working
        return "anthropic"
    if forced == "off":
        forced = "auto"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if _claude_cli():
        return "claude_cli"
    return None


def default_model(transport: str | None = None) -> str:
    """The model id this environment records under.

    BONDLAYER_MODEL wins outright. Changing either the transport's default or
    this variable changes the fixture key, so the demo will miss its cache and
    want to re-record -- which is the intended behaviour, not a bug: a fixture
    recorded from a different model is a different experiment.
    """
    override = os.environ.get("BONDLAYER_MODEL")
    if override:
        return override
    transport = transport or configured_transport() or "anthropic"
    return DEFAULT_MODELS.get(transport, MODEL)


def chat_model() -> str:
    """The model id for the live chat, which is always OpenAI.

    `BONDLAYER_MODEL` means "the model for the configured transport", and this
    function is not the configured transport unless that transport is openai.
    Honouring it unconditionally is how the demo came to send
    `claude-sonnet-5` to `api.openai.com` and take a 404 in front of a
    shopper: the variable had been set so the *ranking fixtures* would hit, and
    it silently retargeted a completely different code path.

    `BONDLAYER_CHAT_MODEL` overrides this alone, for when the two genuinely
    need to differ.
    """
    explicit = os.environ.get("BONDLAYER_CHAT_MODEL")
    if explicit:
        return explicit
    if configured_transport() == "openai":
        return os.environ.get("BONDLAYER_MODEL") or DEFAULT_MODELS["openai"]
    return DEFAULT_MODELS["openai"]


def available_transport() -> str | None:
    """Which live transport would actually answer right now, if any.

    BONDLAYER_LLM=off forces fixtures only -- useful on stage, where an
    accidental live call is the last thing anyone wants.
    """
    if os.environ.get("BONDLAYER_LLM", "auto").lower() == "off":
        return None
    transport = configured_transport()
    if transport == "openai" and not os.environ.get("OPENAI_API_KEY"):
        return None
    if transport == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    if transport == "claude_cli" and not _claude_cli():
        return None
    return transport


def _call_openai(
    system: str, prompt: str, model: str, max_tokens: int
) -> tuple[str, dict]:
    """Record through the OpenAI Chat Completions API.

    Parameter support varies by model generation -- the reasoning models reject
    `temperature` and want `max_completion_tokens` where the older ones want
    `max_tokens`. Rather than hard-code a table that goes stale, send the
    strict, reproducible form first and drop whichever parameter the API names
    in its complaint. The retry is logged into the usage block so a run that
    silently lost temperature=0 is visible in the transcript rather than
    quietly non-deterministic (D5 wants the baseline pinned).
    """
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise LLMUnavailable("openai package not installed (pip install openai)") from exc

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    params: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,  # D5: the baseline must be reproducible.
        "max_tokens": max_tokens,
    }
    # A reasoning model spends the completion budget thinking before it emits a
    # token, so a budget sized for the answer returns an empty string with
    # finish_reason=length -- or, on newer API versions, a 400 naming
    # max_tokens. That is exactly how this repo acquired two empty gpt-5
    # fixtures and then silently ranked on list price for a week. Ask for low
    # effort and real headroom; both are dropped below if the model rejects
    # them, so this stays safe for non-reasoning models.
    if _is_reasoning_model(model):
        params["reasoning_effort"] = "low"
        params["max_tokens"] = max(max_tokens, REASONING_HEADROOM_TOKENS)
    dropped: list[str] = []

    for _ in range(6):
        try:
            resp = client.chat.completions.create(**params)
            break
        except Exception as exc:
            message = str(exc)
            if "max_completion_tokens" in message and "max_tokens" in params:
                params["max_completion_tokens"] = params.pop("max_tokens")
                dropped.append("max_tokens->max_completion_tokens")
                continue
            # "Could not finish ... max_tokens or model output limit was
            # reached." The budget is the problem, not the parameter name.
            budget_key = "max_completion_tokens" if "max_completion_tokens" in params else "max_tokens"
            if "output limit was reached" in message or "higher max_tokens" in message:
                current = params.get(budget_key, max_tokens)
                if current < REASONING_CEILING_TOKENS:
                    params[budget_key] = min(current * 4, REASONING_CEILING_TOKENS)
                    dropped.append(f"raised {budget_key} to {params[budget_key]}")
                    continue
            if "reasoning_effort" in params and "reasoning_effort" in message:
                params.pop("reasoning_effort")
                dropped.append("dropped reasoning_effort")
                continue
            unsupported = next(
                (p for p in ("temperature", "max_tokens", "max_completion_tokens")
                 if p in params and f"'{p}'" in message),
                None,
            )
            if unsupported is None:
                raise LLMUnavailable(f"OpenAI call failed: {message[:300]}") from exc
            params.pop(unsupported)
            dropped.append(f"dropped {unsupported}")
    else:
        raise LLMUnavailable("OpenAI call failed: could not find a supported parameter set")

    text = resp.choices[0].message.content or ""
    usage: dict[str, Any] = {}
    if resp.usage is not None:
        usage = {
            "input_tokens": resp.usage.prompt_tokens,
            "output_tokens": resp.usage.completion_tokens,
        }
    if dropped:
        usage["parameter_fallbacks"] = dropped
    if resp.choices[0].finish_reason == "length":
        usage["truncated"] = True

    # A reasoning model spends the budget on reasoning tokens FIRST and only
    # then writes visible output. Ask gpt-5 for 1500 and the whole allowance
    # can disappear into reasoning, leaving finish_reason="length" and an
    # EMPTY message -- which is how four fixtures in this repo came to hold
    # "" while reporting a successful recording (D9.17). Retry with real
    # headroom rather than returning nothing.
    budget_key = "max_completion_tokens" if "max_completion_tokens" in params else "max_tokens"
    if not text.strip() and resp.choices[0].finish_reason == "length":
        for attempt in range(2):
            params[budget_key] = min(params.get(budget_key, max_tokens) * 4, 32000)
            resp = client.chat.completions.create(**params)
            text = resp.choices[0].message.content or ""
            dropped.append(f"retried with {budget_key}={params[budget_key]}")
            if text.strip():
                break
        usage["parameter_fallbacks"] = dropped
        if resp.usage is not None:
            usage["output_tokens"] = resp.usage.completion_tokens
        usage["truncated"] = resp.choices[0].finish_reason == "length"

    return text, usage


def _call_anthropic(
    system: str, prompt: str, model: str, max_tokens: int
) -> tuple[str, dict]:
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise LLMUnavailable("anthropic package not installed") from exc

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=0,  # D5: the baseline must be reproducible.
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    return text, {
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
    }


def _call_claude_cli(
    system: str, prompt: str, model: str, max_tokens: int
) -> tuple[str, dict]:
    """Record through the local Claude Code CLI in headless mode.

    `--system-prompt-file` replaces the CLI's own system prompt outright, so
    the model sees the agent's system prompt and nothing else of ours.
    `--max-turns 1` with an empty tool allowlist keeps it a single completion
    rather than an agent loop.
    """
    exe = _claude_cli()
    if not exe:
        raise LLMUnavailable("claude CLI not found on PATH")

    alias = {"claude-sonnet-5": "sonnet", "claude-opus-5": "opus"}.get(model, model)

    with tempfile.TemporaryDirectory() as tmp:
        sys_path = Path(tmp) / "system.txt"
        sys_path.write_text(system, encoding="utf-8")
        proc = subprocess.run(
            [
                exe, "-p",
                "--model", alias,
                "--system-prompt-file", str(sys_path),
                "--max-turns", "1",
                "--allowedTools", "",
                "--output-format", "json",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,
        )

    if proc.returncode != 0:
        raise LLMUnavailable(
            f"claude CLI exited {proc.returncode}: {(proc.stderr or '').strip()[:300]}"
        )
    try:
        blob = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise LLMUnavailable(
            f"claude CLI returned non-JSON: {proc.stdout[:200]}"
        ) from exc
    if blob.get("is_error"):
        raise LLMUnavailable(f"claude CLI error: {blob.get('result')}")

    u = blob.get("usage") or {}
    usage = {
        "input_tokens": (
            u.get("input_tokens", 0)
            + u.get("cache_read_input_tokens", 0)
            + u.get("cache_creation_input_tokens", 0)
        ),
        "output_tokens": u.get("output_tokens", 0),
        "cost_usd": blob.get("total_cost_usd"),
        "cli_session_id": blob.get("session_id"),
    }
    return blob.get("result", ""), usage


# ----------------------------------------------------------------------
# The call
# ----------------------------------------------------------------------

TRANSPORTS = {
    "openai": _call_openai,
    "anthropic": _call_anthropic,
    "claude_cli": _call_claude_cli,
}


def complete(
    system: str,
    prompt: str,
    *,
    model: str | None = None,
    max_tokens: int = 1500,
    label: str = "call",
    allow_network: bool = True,
) -> str:
    """Return the model's text, from fixture if one exists.

    `model` defaults to whatever this environment records under, so switching
    provider is a matter of setting OPENAI_API_KEY and re-recording rather
    than of editing call sites.

    Whether it came from disk or the wire, the call lands in TRANSCRIPT with
    its provenance attached.
    """
    model = model or default_model()
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    path = FIXTURE_DIR / f"{label}-{_key(system, prompt, model)}.json"

    if path.exists():
        blob = json.loads(path.read_text(encoding="utf-8"))
        source = blob.get("source") or ("authored" if blob.get("authored") else "unknown")
        if not (blob.get("completion") or "").strip():
            # A fixture recording an empty completion is a botched recording,
            # not a model answer. Replaying it drops the caller into the
            # price-rank fallback, which still prints a confident winner --
            # the exact silent degradation this demo exists to refuse.
            raise LLMUnavailable(
                f"{path.name} holds an EMPTY completion (recorded from "
                f"{blob.get('model', '?')}"
                + (", truncated: the model's budget was spent on reasoning tokens"
                   if (blob.get("usage") or {}).get("truncated") else "")
                + "). Delete it and re-run scripts/seed_fixtures.py --force."
            )
        TRANSCRIPT.append(
            CallRecord(
                label=label,
                model=blob.get("model", model),
                system=system,
                prompt=prompt,
                completion=blob["completion"],
                source=source,
                served_from="fixture",
                fixture=path.name,
                recorded_at=blob.get("recorded_at"),
                latency_ms=blob.get("latency_ms"),
                usage=blob.get("usage") or {},
            )
        )
        return blob["completion"]

    transport = available_transport() if allow_network else None
    if transport is None:
        raise LLMUnavailable(
            f"no fixture at {path.name} and "
            + (
                "network disabled"
                if not allow_network
                else "no OPENAI_API_KEY, no ANTHROPIC_API_KEY and no claude CLI "
                     "on PATH"
            )
        )

    started = time.monotonic()
    text, usage = TRANSPORTS[transport](system, prompt, model, max_tokens)
    latency_ms = int((time.monotonic() - started) * 1000)
    recorded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if not text.strip():
        # Never write an empty completion to disk. Once it is a file it is
        # indistinguishable from a real recording -- it carries a source, a
        # timestamp and a token count -- and every later run replays it and
        # falls back without saying why.
        raise LLMUnavailable(
            f"{transport} returned an EMPTY completion for {label} "
            f"({model}, {usage.get('output_tokens')} output tokens"
            + (", truncated" if usage.get("truncated") else "")
            + "). Nothing was written to disk."
        )

    path.write_text(
        json.dumps(
            {
                "label": label,
                "model": model,
                "source": transport,
                "recorded_at": recorded_at,
                "latency_ms": latency_ms,
                "usage": usage,
                "system": system,
                "prompt": prompt,
                "completion": text,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    TRANSCRIPT.append(
        CallRecord(
            label=label, model=model, system=system, prompt=prompt, completion=text,
            source=transport, served_from="live", fixture=path.name,
            recorded_at=recorded_at, latency_ms=latency_ms, usage=usage,
        )
    )
    return text


def stream_openai(
    system: str,
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    max_tokens: int = 4000,
    label: str = "chat",
):
    """Stream a live multi-turn completion from OpenAI, token by token.

    Deliberately NOT fixture-backed. `complete()` exists to make a scripted
    single-shot run reproducible on stage; this is the opposite -- a real
    conversation, typed live, that nobody recorded in advance. The two must not
    share a cache, or a follow-up question would be answered from a fixture
    recorded for a different question and the transcript would say "replayed"
    for something the shopper had just invented.

    Yields text deltas, then appends the finished call to TRANSCRIPT so the
    transcript overlay carries live turns alongside replayed ones.
    """
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise LLMUnavailable("openai package not installed (pip install openai)") from exc

    if not os.environ.get("OPENAI_API_KEY"):
        raise LLMUnavailable(
            "no OPENAI_API_KEY -- the live chat always talks to OpenAI, "
            "whatever BONDLAYER_LLM is set to"
        )

    model = model or chat_model()
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    payload = [{"role": "system", "content": system}] + messages

    # gpt-5 spends completion budget on reasoning before it emits a token, and
    # a ranking answer that runs out mid-sentence returns "" with
    # finish_reason=length -- which is exactly how this repo ended up with two
    # empty fixtures. Ask for enough headroom, and drop parameters the model
    # rejects rather than guessing a per-model table.
    params: dict[str, Any] = {
        "model": model,
        "messages": payload,
        "max_completion_tokens": max_tokens,
        "stream": True,
        # A reasoning model emits nothing at all until it has finished
        # thinking. At default effort that was 33 s of blank screen before the
        # first token -- unusable in front of an audience. Low effort answers
        # this task just as well and starts talking in a few seconds.
        "reasoning_effort": "low",
    }

    started = time.monotonic()
    chunks: list[str] = []
    usage: dict[str, Any] = {}

    for attempt in range(4):
        try:
            stream = client.chat.completions.create(**params, stream_options={"include_usage": True})
            for event in stream:
                if event.usage is not None:
                    usage = {
                        "input_tokens": event.usage.prompt_tokens,
                        "output_tokens": event.usage.completion_tokens,
                    }
                if not event.choices:
                    continue
                delta = event.choices[0].delta.content
                if delta:
                    chunks.append(delta)
                    yield delta
            break
        except Exception as exc:
            message = str(exc)
            if attempt == 0 and "max_completion_tokens" in message:
                params["max_tokens"] = params.pop("max_completion_tokens")
                continue
            if "reasoning_effort" in message and "reasoning_effort" in params:
                params.pop("reasoning_effort")
                continue
            if attempt < 2 and "stream_options" in message:
                continue
            raise LLMUnavailable(f"OpenAI stream failed: {message[:300]}") from exc

    text = "".join(chunks)
    TRANSCRIPT.append(
        CallRecord(
            label=label,
            model=model,
            system=system,
            prompt=json.dumps(messages, indent=2),
            completion=text,
            source="openai",
            served_from="live",
            recorded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            latency_ms=int((time.monotonic() - started) * 1000),
            usage=usage,
        )
    )


def note_fallback(label: str, reason: str) -> None:
    """Record that no model answered, so the transcript never has a hole in it."""
    TRANSCRIPT.append(
        CallRecord(
            label=label, model="-", system="", prompt="", completion=reason,
            source="fallback", served_from="none",
        )
    )


def extract_json(text: str) -> object:
    """Pull the first JSON value out of a model response."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    start = min(
        (i for i in (text.find("{"), text.find("[")) if i != -1),
        default=-1,
    )
    if start == -1:
        raise ValueError("no JSON found in model response")
    decoder = json.JSONDecoder()
    value, _ = decoder.raw_decode(text[start:])
    return value
