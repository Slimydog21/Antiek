#!/bin/bash
# Parallel noninteractive PR reviews: claude -p + glmf-codex review + grok --single.
# Usage: ./scripts/anti-ek-swarm-review.sh [base-ref]
# Writes /tmp/antiek-swarm-review-{claude,glmf,grok}.txt — no secrets.
set -euo pipefail
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$HOME/.kimi-code/bin:$PATH"
BASE="${1:-origin/main}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
DIFF_FILE="${ANTIEK_SWARM_DIFF:-/tmp/antiek-swarm-pr.diff}"
git fetch origin "$(echo "$BASE" | sed "s#origin/##")" 2>/dev/null || true
# Product-path diff when those files changed; else full branch diff.
if git diff --name-only "${BASE}...HEAD" | grep -qE '^(interfaces/research/api/books.py|interfaces/research/api/upload_routes.py|tests/test_sources_upload.py)$'; then
  git diff "${BASE}...HEAD" -- \
    interfaces/research/api/books.py \
    interfaces/research/api/upload_routes.py \
    tests/test_sources_upload.py \
    docs/anti-ek-mac-mini-dogfood.md \
    > "$DIFF_FILE"
else
  git diff "${BASE}...HEAD" > "$DIFF_FILE"
fi
PROMPT="You are reviewing an Antiek PR diff. Focus ONLY on high-confidence issues:
1) §9.0 rights: gated/personal text must not leak on public paths
2) HTML trust: only sanitized sidecar / is_trusted_sanitized may be content_format=html
3) Auth: unauthenticated_local must not gain owner_read
4) DuckDB: no second writer; no prod DB reset
5) Dual-structure: DuckDB is truth; HTML sidecar is a projection
Output: (a) blocking findings with file:line (b) non-blocking nits (c) LGTM if clean.
Do not suggest weakening gates."

echo "Diff lines: $(wc -l < "$DIFF_FILE")  (file $DIFF_FILE)"
echo "PATH claude=$(command -v claude) glmf=$(command -v glmf-codex) grok=$(command -v grok)"

claude -p "${PROMPT}

$(cat "$DIFF_FILE")" --output-format text \
  > /tmp/antiek-swarm-review-claude.txt 2>&1 &
CPID=$!

# Mini gotcha (Codex 0.154.0): `review --base` cannot take a positional PROMPT.
if command -v glmf-codex >/dev/null; then
  glmf-codex review --base "$BASE" \
    > /tmp/antiek-swarm-review-glmf.txt 2>&1 &
  GPID=$!
elif command -v glm-codex >/dev/null; then
  glm-codex review --base "$BASE" \
    > /tmp/antiek-swarm-review-glmf.txt 2>&1 &
  GPID=$!
else
  GPID=""
fi

if command -v grok >/dev/null; then
  grok --single "Product/UI adversary. ${PROMPT}

$(cat "$DIFF_FILE")" --disable-web-search \
    > /tmp/antiek-swarm-review-grok.txt 2>&1 &
  RPID=$!
else
  RPID=""
fi

wait "$CPID" || true
[ -n "$GPID" ] && wait "$GPID" || true
[ -n "$RPID" ] && wait "$RPID" || true
echo "Wrote /tmp/antiek-swarm-review-claude.txt"
[ -f /tmp/antiek-swarm-review-glmf.txt ] && echo "Wrote /tmp/antiek-swarm-review-glmf.txt"
[ -f /tmp/antiek-swarm-review-grok.txt ] && echo "Wrote /tmp/antiek-swarm-review-grok.txt"
