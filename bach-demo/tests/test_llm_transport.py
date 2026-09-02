"""Transport-layer tests.

Not invariants of the pitch -- those live in test_invariants.py. These cover
the one piece of the client that cannot be exercised without a live key and
would therefore fail for the first time in front of a judge.

The OpenAI parameter-fallback loop exists because parameter support varies by
model generation: the reasoning models reject `temperature` and want
`max_completion_tokens` where older ones want `max_tokens`. Hard-coding which
model wants what goes stale; asking the API and adapting does not. But that
means the adaptation itself is the thing that has to be right.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bondlayer import llm  # noqa: E402


class _Usage:
    prompt_tokens = 11
    completion_tokens = 22


class _Message:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content, finish_reason="stop"):
        self.message = _Message(content)
        self.finish_reason = finish_reason


class _Response:
    def __init__(self, content, finish_reason="stop"):
        self.choices = [_Choice(content, finish_reason)]
        self.usage = _Usage()


class _FakeCompletions:
    """Rejects named parameters the way the real API does, then succeeds."""

    def __init__(self, rejects, finish_reason="stop"):
        self.rejects = list(rejects)
        self.finish_reason = finish_reason
        self.calls: list[dict] = []

    def create(self, **params):
        self.calls.append(dict(params))
        for name, message in self.rejects:
            if name in params:
                raise RuntimeError(message)
        return _Response("the completion", self.finish_reason)


def _install_fake(monkeypatch, completions):
    """Stand in for `from openai import OpenAI` inside _call_openai."""
    import types

    class _FakeClient:
        def __init__(self, api_key=None):
            self.chat = types.SimpleNamespace(completions=completions)

    monkeypatch.setitem(
        sys.modules, "openai", types.SimpleNamespace(OpenAI=_FakeClient)
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


def test_openai_sends_the_strict_reproducible_form_first(monkeypatch):
    """D5 wants the baseline pinned, so temperature=0 must be the first ask."""
    completions = _FakeCompletions(rejects=[])
    _install_fake(monkeypatch, completions)

    text, usage = llm._call_openai("sys", "prompt", "gpt-test", 1500)

    assert text == "the completion"
    assert completions.calls[0]["temperature"] == 0
    assert completions.calls[0]["max_tokens"] == 1500
    assert usage["output_tokens"] == 22
    assert "parameter_fallbacks" not in usage


def test_a_model_that_rejects_temperature_still_records(monkeypatch):
    completions = _FakeCompletions(
        rejects=[("temperature", "Unsupported value: 'temperature' is not supported")]
    )
    _install_fake(monkeypatch, completions)

    text, usage = llm._call_openai("sys", "prompt", "gpt-test", 1500)

    assert text == "the completion"
    assert "temperature" not in completions.calls[-1]
    # The loss of determinism has to be visible in the transcript, not silent:
    # a run that quietly dropped temperature=0 is no longer a pinned baseline.
    assert usage["parameter_fallbacks"] == ["dropped temperature"]


def test_max_tokens_is_renamed_rather_than_dropped(monkeypatch):
    """Dropping it instead would let a long reply truncate at the API default."""
    completions = _FakeCompletions(
        rejects=[("max_tokens", "Use 'max_completion_tokens' instead")]
    )
    _install_fake(monkeypatch, completions)

    llm._call_openai("sys", "prompt", "gpt-test", 1500)

    assert completions.calls[-1]["max_completion_tokens"] == 1500
    assert "max_tokens" not in completions.calls[-1]


def test_both_parameters_can_be_fixed_in_one_call(monkeypatch):
    completions = _FakeCompletions(
        rejects=[
            ("max_tokens", "Use 'max_completion_tokens' instead"),
            ("temperature", "Unsupported value: 'temperature' is not supported"),
        ]
    )
    _install_fake(monkeypatch, completions)

    text, usage = llm._call_openai("sys", "prompt", "gpt-test", 1500)

    assert text == "the completion"
    assert completions.calls[-1]["max_completion_tokens"] == 1500
    assert "temperature" not in completions.calls[-1]
    assert len(usage["parameter_fallbacks"]) == 2


def test_an_unrelated_failure_is_not_retried_into_silence(monkeypatch):
    """A bad key must surface as itself, not as 'could not find a parameter set'."""
    completions = _FakeCompletions(
        rejects=[("model", "AuthenticationError: incorrect API key provided")]
    )
    _install_fake(monkeypatch, completions)

    with pytest.raises(llm.LLMUnavailable, match="incorrect API key"):
        llm._call_openai("sys", "prompt", "gpt-test", 1500)

    assert len(completions.calls) == 1


def test_a_truncated_reply_is_flagged(monkeypatch):
    """A cut-off completion produces invalid JSON downstream; say why."""
    completions = _FakeCompletions(rejects=[], finish_reason="length")
    _install_fake(monkeypatch, completions)

    _, usage = llm._call_openai("sys", "prompt", "gpt-test", 1500)

    assert usage["truncated"] is True


def test_switching_provider_changes_the_fixture_key(monkeypatch):
    """Otherwise an OpenAI run would silently replay Anthropic's recordings.

    The fixture key hashes the model id precisely so that a fixture from a
    different model cannot be passed off as this run's evidence.
    """
    anthropic_key = llm._key("sys", "prompt", "claude-sonnet-5")
    openai_key = llm._key("sys", "prompt", "gpt-5")
    assert anthropic_key != openai_key


def test_provenance_counts_every_recorded_source():
    counts = llm.fixture_provenance()
    assert counts["recorded"] == sum(counts[s] for s in llm.RECORDED_SOURCES)
