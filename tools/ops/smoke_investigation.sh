#!/usr/bin/env bash
# Production smoke for the substrate's Loop-1 happy path.
#
# Fires a small investigation against ``api.antiek.ai``, polls the
# event log until terminal, and asserts ``investigation.completed``.
# Use as a nightly cron / pre-deploy check / "is the substrate
# actually healthy" diagnostic.
#
# Why bash + curl rather than a substrate-internal pytest: this
# exercises the production endpoint, the real dispatch chain, the
# real DuckDB, and the real event log. A green smoke means the
# whole stack is wired correctly. A red smoke is the first place to
# look when post-deploy something is wrong.
#
# History: written 2026-05-18 after the H2 substrate regression
# sweep. The four bugs surfaced during the Hermes cut-over
# (cache-readonly, sub_question null, knowledge_extractor missing,
# Phase 8 postcondition) would have been caught at deploy time if
# this smoke had existed. Now it does.
#
# Exit codes:
#   0  smoke passed (investigation.completed within timeout)
#   1  smoke FAILED (investigation.failed or unhandled error)
#   2  timed out (no terminal event after $SMOKE_TIMEOUT_S)
#   3  bad invocation (missing curl/ssh/jq, etc.)
#
# Required env (default values shown):
#   ANTIEK_API_URL=https://api.antiek.ai
#   ANTIEK_SSH_KEY=$HOME/.ssh/antiek_ed25519
#   ANTIEK_SSH_TARGET=root@167.235.202.98
#   ANTIEK_EVENTS_DIR=/home/antiek/.antiek/research_events
#   SMOKE_TIMEOUT_S=300

set -euo pipefail

API_URL="${ANTIEK_API_URL:-https://api.antiek.ai}"
SSH_KEY="${ANTIEK_SSH_KEY:-$HOME/.ssh/antiek_ed25519}"
SSH_TARGET="${ANTIEK_SSH_TARGET:-root@167.235.202.98}"
EVENTS_DIR="${ANTIEK_EVENTS_DIR:-/home/antiek/.antiek/research_events}"
SMOKE_TIMEOUT_S="${SMOKE_TIMEOUT_S:-300}"
# H4: operator bearer. When set, attached to all api.antiek.ai
# requests as ``Authorization: Bearer <token>``. Source it from the
# same place the substrate reads ANTIEK_OPERATOR_TOKEN to avoid
# token-drift surprises.
OP_TOKEN="${ANTIEK_OPERATOR_TOKEN:-}"
AUTH_HEADER=()
if [ -n "$OP_TOKEN" ]; then
  AUTH_HEADER=(-H "Authorization: Bearer $OP_TOKEN")
fi

INV_ID="smoke_$(date +%Y%m%d_%H%M%S)_$$"
QUESTION="${SMOKE_QUESTION:-Will high-bandwidth memory supply constraints meaningfully limit datacenter GPU deployments through 2027?}"

for cmd in curl ssh scp jq; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "smoke: missing required command: $cmd" >&2
    exit 3
  fi
done

echo "smoke: firing investigation $INV_ID at $API_URL"
resp=$(curl -fsS -X POST "$API_URL/investigations" \
  "${AUTH_HEADER[@]}" \
  -H 'Content-Type: application/json' \
  -d "$(jq -nc --arg q "$QUESTION" --arg id "$INV_ID" \
    '{question: $q, investigation_id: $id}')") || {
  echo "smoke: investigation POST failed" >&2
  exit 1
}
echo "smoke: accepted: $(echo "$resp" | jq -c '{investigation_id, status}')"

deadline=$(( $(date +%s) + SMOKE_TIMEOUT_S ))
local_log="/tmp/${INV_ID}.jsonl"
while [ "$(date +%s)" -lt "$deadline" ]; do
  if scp -q -i "$SSH_KEY" "$SSH_TARGET:${EVENTS_DIR}/${INV_ID}.jsonl" \
       "$local_log" 2>/dev/null \
     && grep -qE 'investigation\.(completed|failed)' "$local_log" 2>/dev/null; then
    break
  fi
  sleep 4
done

if ! grep -qE 'investigation\.(completed|failed)' "$local_log" 2>/dev/null; then
  echo "smoke: TIMEOUT after ${SMOKE_TIMEOUT_S}s — no terminal event" >&2
  exit 2
fi

terminal=$(jq -r 'select(.action_type|test("investigation.(completed|failed)")) | .action_type' \
  "$local_log" | head -1)
hermes_n=$(jq -r 'select(.action_type=="dispatch.call") | .payload.provider' "$local_log" \
  | grep -c '^hermes$' || true)
fallback_n=$(jq -r 'select(.action_type=="dispatch.call") | .payload.provider' "$local_log" \
  | grep -c '^openrouter$' || true)
err_n=$(jq -r 'select(.action_type=="dispatch.call") | .payload.finish_reason' "$local_log" \
  | grep -c '^error$' || true)

echo "smoke: ${terminal}; dispatch.call: hermes=${hermes_n} fallback=${fallback_n} errors=${err_n}"

if [ "$terminal" = "investigation.completed" ]; then
  exit 0
fi
echo "smoke: FAILED — see $local_log for full trajectory" >&2
exit 1
