#!/bin/bash
# Parallel noninteractive PR reviews (claude + glmf-codex by default).
# Usage: ./scripts/swarm-review-pr.sh [base-ref]
# Writes /tmp/antiek-swarm-review-{claude,glmf}.txt — no secrets.
set -euo pipefail
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$HOME/.kimi-code/bin:$PATH"
BASE="${1:-origin/main}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
DIFF_FILE="${ANTIEK_SWARM_DIFF:-/tmp/antiek-swarm-pr.diff}"
git fetch origin "$(echo "$BASE" | sed "s#origin/##")" 2>/dev/null || true
git diff "${BASE}...HEAD" > "$DIFF_FILE"
PROMPT="You are reviewing an Antiek PR diff. Focus ONLY on high-confidence issues:
1) §9.0 rights: gated/personal text must not leak on public paths
2) HTML trust: only sanitized sidecar / is_trusted_sanitized may be content_format=html
3) Auth: unauthenticated_local must not gain owner_read
4) DuckDB: no second writer; no prod DB reset
5) Secrets: no tokens in logs/docs
Output: (a) blocking findings with file:line (b) non-blocking nits (c) LGTM if clean.
Do not suggest weakening gates."

echo "Diff lines: $(wc -l < "$DIFF_FILE")"
claude -p "${PROMPT}

$(cat "$DIFF_FILE")" > /tmp/antiek-swarm-review-claude.txt 2>&1 &
CPID=$!
if command -v glmf-codex >/dev/null; then
  glmf-codex exec "${PROMPT}

$(cat "$DIFF_FILE")" > /tmp/antiek-swarm-review-glmf.txt 2>&1 &
  GPID=$!
elif command -v glm-codex >/dev/null; then
  glm-codex exec "${PROMPT}

$(cat "$DIFF_FILE")" > /tmp/antiek-swarm-review-glmf.txt 2>&1 &
  GPID=$!
else
  GPID=""
fi
wait "$CPID" || true
[ -n "$GPID" ] && wait "$GPID" || true
echo "Wrote /tmp/antiek-swarm-review-claude.txt"
[ -f /tmp/antiek-swarm-review-glmf.txt ] && echo "Wrote /tmp/antiek-swarm-review-glmf.txt"
