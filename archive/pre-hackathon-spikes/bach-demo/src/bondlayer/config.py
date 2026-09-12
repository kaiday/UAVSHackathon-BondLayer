"""Load `.env` into the process environment.

Keys and provider choice live in `demo/.env`, which is git-ignored. `.env` is
read once, at import of the `bondlayer` package, so every entry point --
`run_demo.py`, the Streamlit app, `scripts/seed_fixtures.py`, pytest -- gets
the same configuration without any of them having to remember to ask for it.

Deliberately dependency-free. `python-dotenv` would do this too, but the format
we actually need is a handful of `KEY=value` lines, and a hackathon laptop with
one fewer pip install that can fail on the morning is worth more than the edge
cases it handles.

**A real environment variable always wins.** `.env` only fills in what is not
already set, which is the usual dotenv convention and the one that makes

    OPENAI_API_KEY=... python run_demo.py compare --live

behave the way anyone would expect. Set `BONDLAYER_ENV_FILE` to point somewhere
else, or to an empty string to skip loading entirely.
"""

from __future__ import annotations

import os
from pathlib import Path

#: demo/ -- the directory holding run_demo.py.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

#: Set by load_env() to the file it read, or None. Reported in the CLI and UI
#: banners so "why is it not picking up my key" is answerable at a glance.
LOADED_FROM: Path | None = None

#: Names loaded from .env this run. Names only -- never values, because these
#: are secrets and the banners that show this are on a projector.
LOADED_KEYS: list[str] = []


def _parse(text: str) -> list[tuple[str, str]]:
    """KEY=value lines. Comments, blanks, `export ` prefixes and surrounding
    quotes are tolerated because every .env anyone pastes in has them."""
    pairs: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        pairs.append((key, value))
    return pairs


def env_path() -> Path | None:
    """Which file load_env() would read, if any."""
    override = os.environ.get("BONDLAYER_ENV_FILE")
    if override is not None:
        return Path(override) if override.strip() else None
    return PROJECT_ROOT / ".env"


def load_env() -> Path | None:
    """Fill in unset variables from `.env`. Safe to call more than once."""
    global LOADED_FROM

    path = env_path()
    if path is None or not path.is_file():
        return None

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    for key, value in _parse(text):
        if key not in os.environ:
            os.environ[key] = value
            if key not in LOADED_KEYS:
                LOADED_KEYS.append(key)

    LOADED_FROM = path
    return path


def describe() -> str:
    """One line for the banners. Names the file and the keys, never a value."""
    if LOADED_FROM is None:
        path = env_path()
        if path is None:
            return "no .env (BONDLAYER_ENV_FILE is empty)"
        return f"no .env at {path}"
    if not LOADED_KEYS:
        return f".env at {LOADED_FROM} read; every name in it was already set"
    return f".env loaded from {LOADED_FROM}: {', '.join(sorted(LOADED_KEYS))}"
