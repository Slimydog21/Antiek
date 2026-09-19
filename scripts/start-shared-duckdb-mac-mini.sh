#!/bin/bash
set -euo pipefail
export PATH="/opt/homebrew/bin:$PATH"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WT="${ANTIEK_WORKTREE:-$REPO_ROOT}"
PL="${ANTIEK_PLATFORM:-/Users/slimydog/Antiek/platform}"
LOG=/tmp/antiek-anti-ek
HOME_ISO="$WT/.antiek-home"
EVENTS_ISO="$HOME_ISO/research_events_isolated"
SHARED_HOME="${ANTIEK_SHARED_HOME:-/Users/slimydog/.antiek}"
SHARED_DB="${ANTIEK_DUCKDB_PATH:-$SHARED_HOME/research_graph.duckdb}"
# Shared promote pointer — survives tip-sync / worktree swaps (same class as DuckDB).
SHARED_TPUF="${ANTIEK_TURBOPUFFER_MANIFEST_DIR:-$SHARED_HOME/turbopuffer-shadow}"
FLYWHEEL_SEED="$SHARED_HOME/flywheel-seed"
mkdir -p "$LOG" "$HOME_ISO" "$EVENTS_ISO" "$SHARED_TPUF" "$FLYWHEEL_SEED"

# Stop prior API on :8000
if [ -f "$LOG/api.pid" ] && kill -0 "$(cat "$LOG/api.pid")" 2>/dev/null; then
  kill "$(cat "$LOG/api.pid")" || true
  sleep 2
fi
if lsof -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  kill $(lsof -t -iTCP:8000 -sTCP:LISTEN) 2>/dev/null || true
  sleep 1
fi
# Clear stale duckdb write lock if holder is dead
if [ -f "$SHARED_DB.write.lock" ]; then
  LOCK_PID=$(awk "{print \$1}" "$SHARED_DB.write.lock" 2>/dev/null || true)
  if [ -n "${LOCK_PID:-}" ] && ! kill -0 "$LOCK_PID" 2>/dev/null; then
    rm -f "$SHARED_DB.write.lock"
  fi
fi

# Bootstrap shared TurboPuffer shadow from a prior worktree copy if needed.
WT_TPUF="$WT/.antiek/turbopuffer-shadow"
if [ ! -f "$SHARED_TPUF/active.json" ] && [ -f "$WT_TPUF/active.json" ]; then
  cp -R "$WT_TPUF/." "$SHARED_TPUF/"
fi
# One-time migrate: if shared still empty, leave hybrid_ready=false honestly.

# Flywheel seed: isolated events start empty on tip-sync; copy a real
# knowledge.reused trajectory from ~/.antiek/flywheel-seed/ (operator-curated,
# never invent events). Skip if isolated already has reuse evidence.
if ! grep -Rql "knowledge.reused" "$EVENTS_ISO" 2>/dev/null; then
  shopt -s nullglob
  for seed in "$FLYWHEEL_SEED"/*.jsonl; do
    cp "$seed" "$EVENTS_ISO/"
  done
  shopt -u nullglob
fi

cd "$WT"
set -a
# shellcheck disable=SC1091
source "$PL/.env"
set +a
export PYTHONPATH="$WT"
export ANTIEK_HOME="$HOME_ISO"
export ANTIEK_RESEARCH_EVENTS_DIR="$EVENTS_ISO"
export ANTIEK_DUCKDB_PATH="$SHARED_DB"
# Skips DuckDB knowledge-projector recovery (boot/CPU). Loop One still runs
# in-process via EventBroadcaster after spin-research / POST /investigations.
export ANTIEK_DISABLE_EVENT_PROJECTOR_RECOVERY=1
export ANTIEK_BUILD_SHA="$(git rev-parse HEAD)"
export ANTIEK_TURBOPUFFER_MANIFEST_DIR="$SHARED_TPUF"
# SERVABLE hybrid for reuse + Thought Partner (keys from platform/.env).
: "${ANTIEK_TURBOPUFFER_SERVABLE:=}"
export ANTIEK_WEBAUTHN_RP_ID=localhost
export ANTIEK_WEBAUTHN_ORIGINS="http://127.0.0.1:5173,http://localhost:5173"
# Local HTTP dogfood: Secure cookies would be dropped by the browser on :5173/:8000.
# FRONTEND_BASE so /auth/dev-login redirects to Vite, not the API host.
export ANTIEK_COOKIE_INSECURE="${ANTIEK_COOKIE_INSECURE:-1}"
export ANTIEK_FRONTEND_BASE_URL="${ANTIEK_FRONTEND_BASE_URL:-http://127.0.0.1:5173}"

nohup "$PL/.venv/bin/uvicorn" interfaces.research.api.app:app \
  --host 127.0.0.1 --port 8000 --workers 1 \
  >"$LOG/api.log" 2>&1 &
echo $! >"$LOG/api.pid"

# Vite: start only if not already listening
if ! lsof -iTCP:5173 -sTCP:LISTEN >/dev/null 2>&1; then
  cd "$WT/apps/reading"
  nohup npm run dev -- --host 127.0.0.1 --port 5173 >"$LOG/vite.log" 2>&1 &
  echo $! >"$LOG/vite.pid"
fi

{
  echo "Updated: $(TZ=Asia/Riyadh date '+%Y-%m-%d %H:%M %Z')"
  echo "Worktree: $WT"
  echo "SHA: $ANTIEK_BUILD_SHA"
  echo "API: http://127.0.0.1:8000  PID $(cat "$LOG/api.pid")"
  echo "Vite: http://127.0.0.1:5173"
  echo "ANTIEK_DUCKDB_PATH=$ANTIEK_DUCKDB_PATH"
  echo "ANTIEK_RESEARCH_EVENTS_DIR=$ANTIEK_RESEARCH_EVENTS_DIR"
  echo "ANTIEK_TURBOPUFFER_MANIFEST_DIR=$ANTIEK_TURBOPUFFER_MANIFEST_DIR"
  echo "Start: scripts/start-shared-duckdb-mac-mini.sh"
} >"$LOG/STATUS-shared-duckdb.txt"

echo "API PID $(cat "$LOG/api.pid")  DUCKDB=$ANTIEK_DUCKDB_PATH  TPUF=$ANTIEK_TURBOPUFFER_MANIFEST_DIR"
echo "UI http://127.0.0.1:5173/  API http://127.0.0.1:8000/health"
