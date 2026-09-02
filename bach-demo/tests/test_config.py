"""`.env` loading.

Small surface, but it decides which provider answers and whether a key is
found at all, so a mistake here looks like "the demo silently stopped using
the model" rather than like a config bug.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bondlayer import config  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_environment():
    """load_env() writes straight into os.environ, and monkeypatch only undoes
    what monkeypatch itself set.

    Without this, a test that loads a fake OPENAI_API_KEY leaves it set for the
    rest of the session, which flips the default model, which changes the
    fixture key, which makes every test that replays a fixture fail somewhere
    far away with a message about a missing file. That happened; hence the
    fixture and this comment.
    """
    saved_env = dict(os.environ)
    saved_from, saved_keys = config.LOADED_FROM, list(config.LOADED_KEYS)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved_env)
        config.LOADED_FROM = saved_from
        config.LOADED_KEYS[:] = saved_keys


def test_parses_the_shapes_people_actually_paste():
    text = "\n".join([
        "# a comment",
        "",
        "OPENAI_API_KEY=sk-plain",
        'QUOTED="sk-double"',
        "SINGLE='sk-single'",
        "export EXPORTED=sk-exported",
        "  SPACED = sk-spaced  ",
        "EMPTY=",
        "NOT_A_PAIR",
        "WITH_EQUALS=a=b=c",
    ])

    assert dict(config._parse(text)) == {
        "OPENAI_API_KEY": "sk-plain",
        "QUOTED": "sk-double",
        "SINGLE": "sk-single",
        "EXPORTED": "sk-exported",
        "SPACED": "sk-spaced",
        "EMPTY": "",
        "WITH_EQUALS": "a=b=c",
    }


def test_a_real_environment_variable_wins(tmp_path, monkeypatch):
    """Otherwise `OPENAI_API_KEY=... python run_demo.py` would be ignored in
    favour of a stale key in a file, which is the opposite of what anyone
    typing that command means."""
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=from-file\nONLY_IN_FILE=yes\n", encoding="utf-8")

    monkeypatch.setenv("BONDLAYER_ENV_FILE", str(env_file))
    monkeypatch.setenv("OPENAI_API_KEY", "from-shell")
    monkeypatch.delenv("ONLY_IN_FILE", raising=False)

    config.load_env()

    import os
    assert os.environ["OPENAI_API_KEY"] == "from-shell"
    assert os.environ["ONLY_IN_FILE"] == "yes"


def test_a_missing_file_is_not_an_error(tmp_path, monkeypatch):
    """The demo has to run on a machine with no .env at all."""
    monkeypatch.setenv("BONDLAYER_ENV_FILE", str(tmp_path / "nope.env"))
    assert config.load_env() is None


def test_loading_can_be_disabled(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("SHOULD_NOT_LOAD=1\n", encoding="utf-8")
    monkeypatch.setenv("BONDLAYER_ENV_FILE", "")
    monkeypatch.delenv("SHOULD_NOT_LOAD", raising=False)

    assert config.env_path() is None
    config.load_env()

    import os
    assert "SHOULD_NOT_LOAD" not in os.environ


def test_describe_never_prints_a_value(tmp_path, monkeypatch):
    """It goes on a projector."""
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=sk-super-secret-value\n", encoding="utf-8")
    monkeypatch.setenv("BONDLAYER_ENV_FILE", str(env_file))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    config.load_env()
    described = config.describe()

    assert "OPENAI_API_KEY" in described
    assert "sk-super-secret-value" not in described


def test_env_selects_the_transport(tmp_path, monkeypatch):
    """The point of the whole file: a key in .env changes which model answers."""
    from bondlayer import llm

    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=sk-test\n", encoding="utf-8")

    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "BONDLAYER_LLM",
                 "BONDLAYER_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BONDLAYER_ENV_FILE", str(env_file))

    config.load_env()

    assert llm.configured_transport() == "openai"
    assert llm.default_model() == "gpt-5"
