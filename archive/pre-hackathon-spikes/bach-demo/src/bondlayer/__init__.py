"""BondLayer demo spike -- see DECISIONS.md. Not submission code (D0)."""

# Read demo/.env before anything asks the environment for a key or a provider.
# Doing it here rather than in each entry point means run_demo.py, the
# Streamlit app, the fixture recorder and pytest cannot disagree about
# configuration. A real environment variable still wins; see config.py.
from .config import load_env as _load_env

_load_env()
