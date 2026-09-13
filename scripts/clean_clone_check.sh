#!/usr/bin/env bash
# Prove a judge's laptop gets from `git clone` to a working merchant server.
#
#   scripts/clean_clone_check.sh [repo-path-or-url] [branch]
#
# Defaults: the repository this script lives in, at its currently checked-out
# branch. Clones into a temp dir, runs `./run.sh --check` there (fresh venv,
# editable install, pytest), starts the merchant server on a free port, and
# asserts the wire contract:
#
#   GET /voltway/.well-known/ucp                    200, has signing_keys[]
#   GET /voltway/ucp/catalog/search (no header)     >=1 product, NO `extensions`
#   GET /voltway/ucp/catalog/search (ext header)    `extensions` present
#   GET /citycircuit/ucp/catalog/search (ext hdr)   NO `extensions`  (control)
#   GET /onboard/merchants                          list of 3 merchants
#
# Exits non-zero on the first failure. Kills the server and removes the clone
# on exit. Run it from anywhere; needs git, curl and Python 3.12+ (PYTHON=...).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${1:-$(git -C "$HERE" rev-parse --show-toplevel)}"
BRANCH="${2:-$(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null || echo HEAD)}"

TMP="$(mktemp -d "${TMPDIR:-/tmp}/bondlayer-clean-clone.XXXXXX")"
SERVER_PID=""
FAILURES=0

cleanup() {
  if [ -n "$SERVER_PID" ]; then kill "$SERVER_PID" 2>/dev/null || true; wait "$SERVER_PID" 2>/dev/null || true; fi
  rm -rf "$TMP"
}
trap cleanup EXIT INT TERM

pass() { printf 'PASS  %s\n' "$*"; }
fail() { printf 'FAIL  %s\n' "$*" >&2; FAILURES=$((FAILURES + 1)); }

echo "clean-clone check"
echo "  source : $REPO"
echo "  branch : $BRANCH"
echo "  clone  : $TMP/clone"
echo

# -------------------------------------------------------------- 1. clone ----
if [ "$BRANCH" = "HEAD" ]; then
  git clone -q "$REPO" "$TMP/clone"
else
  git clone -q --branch "$BRANCH" "$REPO" "$TMP/clone"
fi
cd "$TMP/clone"
echo "  commit : $(git rev-parse --short HEAD)  $(git log -1 --format=%s | cut -c1-60)"
pass "git clone"

# ------------------------------------------------- 2. setup + test suite ----
[ -x ./run.sh ] || chmod +x ./run.sh
echo
echo "--- ./run.sh --check ---"
if ./run.sh --check 2>&1 | tee "$TMP/check.log"; then
  SUMMARY="$(grep -E '^[0-9]+ passed' "$TMP/check.log" | tail -1 || true)"
  pass "run.sh --check (${SUMMARY:-pytest ran})"
else
  fail "run.sh --check exited non-zero"
  echo "aborting: cannot start a server from a build whose tests did not run" >&2
  exit 1
fi
echo "--- end run.sh --check ---"
echo

VPY="$TMP/clone/.venv/bin/python"

# --------------------------------------------------------- 3. free port ----
PORT="$("$VPY" - <<'PY'
import socket
s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()
PY
)"
BASE="http://127.0.0.1:$PORT"

# ------------------------------------------------------- 4. start server ----
( cd bondlayer && exec "$VPY" run_server.py "$PORT" ) >"$TMP/server.log" 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 60); do
  if curl -sf -o /dev/null "$BASE/voltway/.well-known/ucp" 2>/dev/null; then break; fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then break; fi
  sleep 0.25
done
if curl -sf -o /dev/null "$BASE/voltway/.well-known/ucp"; then
  pass "server up on :$PORT"
else
  fail "server did not answer on :$PORT"; sed 's/^/    /' "$TMP/server.log" >&2; exit 1
fi

# ------------------------------------------------------------- 5. wire ----
# The header must declare catalog.search itself: a capability the agent did
# not declare returns 406, and the extension is pruned when no parent survives.
EXT_HEADER='UCP-Agent: dev.ucp.shopping.catalog.search;dev.ucp.shopping.catalog.lookup;org.bondlayer.benefit_value'
SEARCH='ucp/catalog/search?category=laptop&max_price=1500'

# check <label> <expect-json-python-expression> <curl args...>
check() {
  local label="$1" expr="$2"; shift 2
  local body code
  body="$(curl -s -w '\n%{http_code}' "$@")"
  code="${body##*$'\n'}"; body="${body%$'\n'*}"
  if [ "$code" != "200" ]; then fail "$label -> HTTP $code: $(echo "$body" | cut -c1-120)"; return; fi
  local verdict
  verdict="$(BODY="$body" "$VPY" -c "
import json, os, sys
d = json.loads(os.environ['BODY'])
ok = bool($expr)
print('ok' if ok else 'bad')
" 2>&1)" || true
  if [ "$verdict" = "ok" ]; then pass "$label"; else fail "$label ($verdict)"; fi
}

check "GET /voltway/.well-known/ucp has signing_keys[]" \
  "isinstance(d.get('signing_keys'), list) and len(d['signing_keys']) >= 1" \
  "$BASE/voltway/.well-known/ucp"

check "plain search: >=1 product and NO extensions key" \
  "len(d.get('products', [])) >= 1 and 'extensions' not in d" \
  "$BASE/voltway/$SEARCH"

check "search with extension header: extensions present" \
  "len(d.get('products', [])) >= 1 and 'org.bondlayer.benefit_value' in d.get('extensions', {})" \
  -H "$EXT_HEADER" "$BASE/voltway/$SEARCH"

check "control (citycircuit) with extension header: NO extensions key" \
  "len(d.get('products', [])) >= 1 and 'extensions' not in d" \
  -H "$EXT_HEADER" "$BASE/citycircuit/$SEARCH"

check "GET /onboard/merchants lists 3 merchants" \
  "isinstance(d, list) and len(d) == 3 and all('readiness' in m for m in d)" \
  "$BASE/onboard/merchants"

# ------------------------------------------------------------- 6. verdict ----
echo
if [ "$FAILURES" -eq 0 ]; then
  echo "clean-clone check: ALL PASS ($(git rev-parse --short HEAD), python $("$VPY" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])'))"
  exit 0
else
  echo "clean-clone check: $FAILURES FAILURE(S)" >&2
  exit 1
fi
