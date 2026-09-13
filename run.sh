#!/usr/bin/env bash
# BondLayer -- one command from a clean clone to the running demo.
#
#   ./run.sh              set up, then start the merchant server (:8000) and,
#                         if buyer-agent is present, the buyer-agent
#                         stand-in (:8001) and its Vite UI (:5173). Ctrl-C stops
#                         everything this script started.
#   ./run.sh --check      set up and run the bondlayer test suite, start nothing
#   ./run.sh --setup      set up only (venv + installs), start nothing
#   ./run.sh --no-agent   merchant server only
#   ./run.sh --no-ui      skip the Vite dev server (the agent serves its own
#                         static page on :8001 regardless)
#   ./run.sh --restart    stop the BondLayer servers already on :8000/:8001
#                         (run_server.py, src.agent.main only), then start fresh
#
# Idempotent: re-running reuses .venv, re-installs are no-ops, and a port that
# is already serving is reported and left alone rather than started twice --
# it keeps the code it was started with, so use --restart after pulling.
# No network is needed at runtime; pip/npm installs are the only downloads.
#
# Env: PYTHON (default python3), BONDLAYER_PORT (8000), AGENT_PORT (8001),
#      UI_PORT (5173).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
VENV="$ROOT/.venv"
MERCHANT_PORT="${BONDLAYER_PORT:-8000}"
AGENT_PORT="${AGENT_PORT:-8001}"
UI_PORT="${UI_PORT:-5173}"
CHAT_APP="$ROOT/buyer-agent"
LOG_DIR="$ROOT/.run"

MODE=run
START_AGENT=1
START_UI=1
RESTART=0
for arg in "$@"; do
  case "$arg" in
    --restart) RESTART=1 ;;
    --check) MODE=check ;;
    --setup) MODE=setup ;;
    --no-agent) START_AGENT=0 ;;
    --no-ui) START_UI=0 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

say() { printf '\n== %s\n' "$*"; }

# ---------------------------------------------------------------- python ----
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "error: $PYTHON not found. Install Python 3.12+ or set PYTHON=/path/to/python" >&2
  exit 1
fi
if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)'; then
  echo "error: bondlayer needs Python 3.12+; $PYTHON is $("$PYTHON" --version 2>&1)" >&2
  exit 1
fi

# ------------------------------------------------------------------ venv ----
say "virtualenv: $VENV"
if [ ! -x "$VENV/bin/python" ]; then
  "$PYTHON" -m venv "$VENV"
  echo "   created with $("$VENV/bin/python" --version)"
else
  echo "   reusing $("$VENV/bin/python" --version)"
fi
VPY="$VENV/bin/python"
VPIP="$VPY -m pip"

# --------------------------------------------------------------- install ----
say "installing bondlayer (editable, with dev extras)"
$VPIP install -q --disable-pip-version-check -e "$ROOT/bondlayer[dev]"

if [ -f "$CHAT_APP/requirements.txt" ]; then
  say "installing buyer-agent requirements"
  # Run from inside chat-app so any relative -e path in its requirements
  # resolves against that directory.
  ( cd "$CHAT_APP" && $VPIP install -q --disable-pip-version-check -r requirements.txt )
else
  echo "   buyer-agent/requirements.txt not present -- merchant server only"
  START_AGENT=0
  START_UI=0
fi

if [ "$MODE" = "setup" ]; then
  say "setup complete. Start with: ./run.sh"
  exit 0
fi

if [ "$MODE" = "check" ]; then
  say "pytest (bondlayer/)"
  ( cd "$ROOT/bondlayer" && "$VPY" -m pytest -q )
  say "check complete"
  exit 0
fi

# --------------------------------------------------------------- helpers ----
port_busy() { "$VPY" - "$1" <<'PY'
import socket, sys
s = socket.socket(); s.settimeout(0.5)
sys.exit(0 if s.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)
PY
}

wait_for() { # url, seconds
  local url="$1" tries="${2:-40}"
  for _ in $(seq 1 "$tries"); do
    if curl -sf -o /dev/null "$url" 2>/dev/null; then return 0; fi
    sleep 0.25
  done
  return 1
}

mkdir -p "$LOG_DIR"
PIDS=()
cleanup() {
  if [ "${#PIDS[@]}" -gt 0 ]; then
    printf '\n== stopping %s\n' "${PIDS[*]}"
    kill "${PIDS[@]}" 2>/dev/null || true
    wait "${PIDS[@]}" 2>/dev/null || true
    PIDS=()
  fi
}
trap cleanup EXIT INT TERM

# Stops only a BondLayer server on a port: the listening process must be
# running the given marker; anything else holding the port is left alone.
stop_listener() { # port, marker
  local port="$1" marker="$2" pid cmd
  if ! command -v lsof >/dev/null 2>&1; then
    echo "   lsof not found -- stop the process on :$port yourself"
    return 0
  fi
  for pid in $(lsof -ti "tcp:$port" -sTCP:LISTEN 2>/dev/null || true); do
    cmd="$(ps -o command= -p "$pid" 2>/dev/null || true)"
    case "$cmd" in
      *"$marker"*) kill "$pid" 2>/dev/null || true; echo "   stopped pid $pid on :$port" ;;
      *) echo "   :$port is held by another program (pid $pid) -- not stopping it" ;;
    esac
  done
  for _ in $(seq 1 40); do
    port_busy "$port" || return 0
    sleep 0.25
  done
}

if [ "$RESTART" = 1 ]; then
  say "restart: stopping BondLayer servers on :$MERCHANT_PORT and :$AGENT_PORT"
  stop_listener "$MERCHANT_PORT" run_server.py
  if [ "$START_AGENT" = 1 ]; then stop_listener "$AGENT_PORT" src.agent.main; fi
fi

# ------------------------------------------------------- merchant server ----
say "merchant server (bondlayer/run_server.py) on :$MERCHANT_PORT"
if port_busy "$MERCHANT_PORT"; then
  echo "   :$MERCHANT_PORT already serving -- leaving it alone (./run.sh --restart loads new code)"
else
  ( cd "$ROOT/bondlayer" && exec "$VPY" run_server.py "$MERCHANT_PORT" ) \
    >"$LOG_DIR/merchant.log" 2>&1 &
  PIDS+=("$!")
  if wait_for "http://127.0.0.1:$MERCHANT_PORT/health"; then
    echo "   up (log: .run/merchant.log)"
  else
    echo "   FAILED to start; tail of .run/merchant.log:" >&2
    tail -n 20 "$LOG_DIR/merchant.log" >&2
    exit 1
  fi
fi

# ------------------------------------------------------------- the agent ----
# Only the agent. buyer-agent/src/merchant is being removed: the merchant
# is bondlayer/'s server, and nothing else is started on :8000.
if [ "$START_AGENT" = 1 ] && [ -f "$CHAT_APP/src/agent/main.py" ]; then
  say "buyer-agent stand-in (buyer-agent: src.agent.main) on :$AGENT_PORT"
  if port_busy "$AGENT_PORT"; then
    echo "   :$AGENT_PORT already serving -- leaving it alone (./run.sh --restart loads new code)"
  else
    # `python -m src.agent.main` hardcodes :8001 and --reload; running the same
    # app through uvicorn honours AGENT_PORT and leaves one process to stop.
    ( cd "$CHAT_APP" && \
      BONDLAYER_MERCHANT_URL="http://127.0.0.1:$MERCHANT_PORT" \
      exec "$VPY" -m uvicorn src.agent.main:app --host 127.0.0.1 --port "$AGENT_PORT" ) \
      >"$LOG_DIR/agent.log" 2>&1 &
    PIDS+=("$!")
    if wait_for "http://127.0.0.1:$AGENT_PORT/" 60; then
      echo "   up (log: .run/agent.log)"
    else
      echo "   did not answer on :$AGENT_PORT yet; see .run/agent.log" >&2
    fi
  fi
elif [ "$START_AGENT" = 1 ]; then
  echo
  echo "== no buyer-agent/src/agent/main.py -- agent not started"
fi

# ----------------------------------------------------------------- the UI ----
UI_DIR="$CHAT_APP/src/ui"
UI_STARTED=0
if [ "$START_AGENT" = 1 ] && [ "$START_UI" = 1 ] && [ -f "$UI_DIR/package.json" ]; then
  if command -v npm >/dev/null 2>&1; then
    say "chat UI (vite) on :$UI_PORT"
    if port_busy "$UI_PORT"; then
      echo "   :$UI_PORT already serving -- leaving it alone"
      UI_STARTED=1
    else
      if [ ! -d "$UI_DIR/node_modules" ]; then
        echo "   npm install (first run only)"
        ( cd "$UI_DIR" && npm install --silent --no-fund --no-audit ) >"$LOG_DIR/ui-install.log" 2>&1 \
          || { echo "   npm install failed; see .run/ui-install.log" >&2; }
      fi
      if [ -d "$UI_DIR/node_modules" ]; then
        ( cd "$UI_DIR" && exec npm run dev -- --port "$UI_PORT" ) >"$LOG_DIR/ui.log" 2>&1 &
        PIDS+=("$!")
        UI_STARTED=1
        echo "   starting (log: .run/ui.log)"
      fi
    fi
  else
    echo
    echo "== npm not found -- skipping the Vite UI; the agent's own page is on :$AGENT_PORT"
  fi
fi

# ------------------------------------------------------------------ URLs ----
say "ready"
echo "   merchant health    http://127.0.0.1:$MERCHANT_PORT/health"
echo "   add a merchant     http://127.0.0.1:$MERCHANT_PORT/console/onboarding/"
echo "   merchant console   http://127.0.0.1:$MERCHANT_PORT/console/"
echo "   onboarding API     http://127.0.0.1:$MERCHANT_PORT/onboard/merchants"
echo "   API docs           http://127.0.0.1:$MERCHANT_PORT/docs"
if [ "$START_AGENT" = 1 ] && [ -f "$CHAT_APP/src/agent/main.py" ]; then
  echo "   buyer agent        http://127.0.0.1:$AGENT_PORT/"
fi
if [ "$UI_STARTED" = 1 ]; then
  echo "   chat UI            http://127.0.0.1:$UI_PORT/"
fi
echo
echo "   Ctrl-C stops what this script started."

if [ "${#PIDS[@]}" -gt 0 ]; then
  wait "${PIDS[@]}"
else
  echo "   (everything was already running; nothing to wait on)"
fi
