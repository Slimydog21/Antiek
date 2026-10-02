#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

python_bin=${ANTIEK_PYTHON:-../../.venv/bin/python}
python_bin=$(command -v "$python_bin")
if [[ "$python_bin" != /* ]]; then python_bin="$PWD/$python_bin"; fi
api_port=${ANTIEK_E2E_API_PORT:-8000}
readiness_seconds=${ANTIEK_E2E_BACKEND_TIMEOUT_SECONDS:-120}
state_dir=$(mktemp -d "${TMPDIR:-/tmp}/antiek-chromium.XXXXXX")
backend_pid=
mkdir -p playwright-report "$state_dir/events"
backend_log="$PWD/playwright-report/backend.log"

cleanup() {
  if [[ -n "$backend_pid" ]]; then
    kill "$backend_pid" 2>/dev/null || true
    wait "$backend_pid" 2>/dev/null || true
  fi
  rm -rf "$state_dir"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# The preview proxy used to target an API that this job never started. Give
# this run its own graph and require HTTP 200 before Playwright can run tests.
# Refuse an occupied port so a local run cannot reuse the operator's backend.
"$python_bin" - "$api_port" <<'PY'
import socket
import sys

port = int(sys.argv[1])
with socket.socket() as listener:
    try:
        listener.bind(("127.0.0.1", port))
    except OSError as error:
        sys.exit(f"backend on :{port} cannot start: {error}")
PY

export ANTIEK_DUCKDB_PATH="$state_dir/graph.duckdb"
export ANTIEK_STATE_DIR="$state_dir"
export ANTIEK_RESEARCH_EVENTS_DIR="$state_dir/events"
export ANTIEK_EVENT_LOG_DIR="$state_dir/events"
export ANTIEK_AUTH_SECRET=playwright-chromium-secret-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
export ANTIEK_OPERATOR_EMAIL=operator@example.com
export ANTIEK_COOKIE_INSECURE=1
export ANTIEK_DISABLE_EVENT_PROJECTOR_RECOVERY=1
export ANTIEK_DEV_API_TARGET="http://127.0.0.1:$api_port"

(
  cd ../..
  "$python_bin" -c 'from substrate.graph import ensure_initialized; ensure_initialized()'
  exec "$python_bin" -m uvicorn interfaces.research.api.app:app --host 127.0.0.1 --port "$api_port" --workers 1
) > "$backend_log" 2>&1 &
backend_pid=$!

if ! node --import tsx scripts/wait_for_http.ts "backend on :$api_port" "$ANTIEK_DEV_API_TARGET/health" "$readiness_seconds"; then
  cat "$backend_log"
  exit 1
fi
if ! kill -0 "$backend_pid" 2>/dev/null; then
  echo "backend on :$api_port exited before Playwright started" >&2
  cat "$backend_log"
  exit 1
fi

npx playwright test "$@"
