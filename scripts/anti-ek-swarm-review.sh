#!/bin/bash
# Parallel noninteractive PR reviews: claude -p + glmf-codex review + grok --single.
#
# Usage:
#   ./scripts/anti-ek-swarm-review.sh --check           # readiness smoke (no model calls)
#   ./scripts/anti-ek-swarm-review.sh --dry-run [base]  # write diff + plan only
#   ./scripts/anti-ek-swarm-review.sh [base-ref]        # parallel reviews
#
# Writes /tmp/antiek-swarm-review-{claude,glmf,grok}.txt — no secrets.
# Cite: docs/anti-ek-cli-swarm.md
set -euo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$HOME/.kimi-code/bin:$PATH"

MODE="review"
BASE="origin/main"
if [[ "${1:-}" == "--check" ]]; then
  MODE="check"
  shift || true
elif [[ "${1:-}" == "--dry-run" ]]; then
  MODE="dry-run"
  shift || true
  BASE="${1:-origin/main}"
elif [[ $# -ge 1 ]]; then
  BASE="$1"
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUT_DIR="${ANTIEK_SWARM_OUT:-/tmp}"
DIFF_FILE="${ANTIEK_SWARM_DIFF:-$OUT_DIR/antiek-swarm-pr.diff}"
CHECK_FILE="${ANTIEK_SWARM_CHECK:-$OUT_DIR/antiek-swarm-check.txt}"
# argv size guard — stuffing multi-MB diffs into claude/grok argv fails silently
MAX_DIFF_BYTES="${ANTIEK_SWARM_MAX_DIFF_BYTES:-200000}"

_have() { command -v "$1" >/dev/null 2>&1; }

_check() {
  {
    echo "anti-ek-swarm-check $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "host=$(hostname 2>/dev/null || echo unknown)"
    echo "cwd=$ROOT"
    echo "PATH_ok=$( [[ ":$PATH:" == *":$HOME/.local/bin:"* ]] && echo yes || echo no )"
    echo
    echo "## CLIs"
    local core_ok=1
    for pair in \
      "claude:reviewer" \
      "grok:adversary" \
      "glmf-codex:implementer-review" \
      "glm-codex:implementer-fallback" \
      "codex:upstream" \
      "mimo:alt-implementer" \
      "kimi:reviewer-backup" \
      "herdr:workspace" \
      "gh:github"; do
      bin="${pair%%:*}"
      role="${pair##*:}"
      if _have "$bin"; then
        ver="$("$bin" --version 2>/dev/null | head -1 | tr -d '\r' || echo present)"
        echo "OK  $bin ($role) -> $(command -v "$bin") :: $ver"
      else
        echo "MISS $bin ($role)"
        case "$bin" in
          claude|grok) core_ok=0 ;;
          glmf-codex)
            _have glm-codex || core_ok=0
            ;;
        esac
      fi
    done
    echo
    echo "## Herdr Antiek w7"
    if _have herdr; then
      if herdr workspace list >"$OUT_DIR/antiek-herdr-workspaces.json" 2>/dev/null; then
        if grep -q '"workspace_id":"w7"' "$OUT_DIR/antiek-herdr-workspaces.json" 2>/dev/null \
          || grep -q '"label":"Antiek"' "$OUT_DIR/antiek-herdr-workspaces.json" 2>/dev/null; then
          echo "OK  Antiek workspace w7 present"
        else
          echo "WARN Antiek w7 not found in herdr workspace list (see $OUT_DIR/antiek-herdr-workspaces.json)"
        fi
      else
        echo "WARN herdr workspace list failed (server down?)"
      fi
    else
      echo "MISS herdr"
    fi
    echo
    echo "## Dogfood worktree"
    for wt in \
      "/Users/slimydog/Antiek/deploy-main-20260917" \
      "/Users/slimydog/Antiek/.worktrees/anti-ek-use-main-20260917"; do
      if [[ -d "$wt" ]]; then
        echo "OK  $wt"
      else
        echo "MISS $wt"
      fi
    done
    echo
    if [[ $core_ok -eq 1 ]]; then
      echo "RESULT core_ready=true (claude + grok + glm*/glmf*)"
      return 0
    else
      echo "RESULT core_ready=false — install missing core CLIs before swarm review"
      return 1
    fi
  } | tee "$CHECK_FILE"
}

if [[ "$MODE" == "check" ]]; then
  _check
  exit $?
fi

git fetch origin "$(echo "$BASE" | sed "s#origin/##")" 2>/dev/null || true

# Prefer product-path diff when those files changed; else full branch diff.
if git diff --name-only "${BASE}...HEAD" 2>/dev/null | grep -qE '^(interfaces/research/api/books.py|interfaces/research/api/upload_routes.py|tests/test_sources_upload.py)$'; then
  git diff "${BASE}...HEAD" -- \
    interfaces/research/api/books.py \
    interfaces/research/api/upload_routes.py \
    tests/test_sources_upload.py \
    docs/anti-ek-mac-mini-dogfood.md \
    > "$DIFF_FILE"
else
  git diff "${BASE}...HEAD" > "$DIFF_FILE" || : > "$DIFF_FILE"
fi

DIFF_BYTES=$(wc -c < "$DIFF_FILE" | tr -d ' ')
if [[ "${DIFF_BYTES:-0}" -gt "$MAX_DIFF_BYTES" ]]; then
  echo "WARN: diff ${DIFF_BYTES} bytes > ${MAX_DIFF_BYTES}; truncating for argv-safe reviews" >&2
  head -c "$MAX_DIFF_BYTES" "$DIFF_FILE" > "${DIFF_FILE}.trunc"
  echo "" >> "${DIFF_FILE}.trunc"
  echo "... [truncated by anti-ek-swarm-review.sh; full file at $DIFF_FILE] ..." >> "${DIFF_FILE}.trunc"
  DIFF_FOR_PROMPT="${DIFF_FILE}.trunc"
else
  DIFF_FOR_PROMPT="$DIFF_FILE"
fi

PROMPT="You are reviewing an Antiek PR diff. Focus ONLY on high-confidence issues:
1) §9.0 rights: gated/personal text must not leak on public paths
2) HTML trust: only sanitized sidecar / is_trusted_sanitized may be content_format=html
3) Auth: unauthenticated_local must not gain owner_read
4) DuckDB: no second writer; no prod DB reset
5) Dual-structure: DuckDB is truth; HTML sidecar is a projection
Output: (a) blocking findings with file:line (b) non-blocking nits (c) LGTM if clean.
Do not suggest weakening gates."

echo "Diff lines: $(wc -l < "$DIFF_FILE" | tr -d ' ')  bytes=$DIFF_BYTES  (file $DIFF_FILE)"
echo "PATH claude=$(command -v claude || echo MISS) glmf=$(command -v glmf-codex || command -v glm-codex || echo MISS) grok=$(command -v grok || echo MISS)"

if [[ "$MODE" == "dry-run" ]]; then
  echo "DRY-RUN: would launch claude/glmf/grok against $DIFF_FOR_PROMPT"
  echo "Prompt bytes: $(printf '%s' "$PROMPT" | wc -c | tr -d ' ')"
  exit 0
fi

CPID=""; GPID=""; RPID=""

if _have claude; then
  claude -p "${PROMPT}

$(cat "$DIFF_FOR_PROMPT")" --output-format text \
    > "$OUT_DIR/antiek-swarm-review-claude.txt" 2>&1 &
  CPID=$!
else
  echo "SKIP claude (not on PATH)" > "$OUT_DIR/antiek-swarm-review-claude.txt"
fi

# Mini gotcha (Codex 0.154.0): `review --base` cannot take a positional PROMPT.
if _have glmf-codex; then
  glmf-codex review --base "$BASE" \
    > "$OUT_DIR/antiek-swarm-review-glmf.txt" 2>&1 &
  GPID=$!
elif _have glm-codex; then
  glm-codex review --base "$BASE" \
    > "$OUT_DIR/antiek-swarm-review-glmf.txt" 2>&1 &
  GPID=$!
else
  echo "SKIP glmf/glm-codex (not on PATH)" > "$OUT_DIR/antiek-swarm-review-glmf.txt"
fi

if _have grok; then
  grok --single "Product/UI adversary. ${PROMPT}

$(cat "$DIFF_FOR_PROMPT")" --disable-web-search \
    > "$OUT_DIR/antiek-swarm-review-grok.txt" 2>&1 &
  RPID=$!
else
  echo "SKIP grok (not on PATH)" > "$OUT_DIR/antiek-swarm-review-grok.txt"
fi

[[ -n "$CPID" ]] && wait "$CPID" || true
[[ -n "$GPID" ]] && wait "$GPID" || true
[[ -n "$RPID" ]] && wait "$RPID" || true

echo "Wrote $OUT_DIR/antiek-swarm-review-claude.txt ($(wc -c < "$OUT_DIR/antiek-swarm-review-claude.txt" | tr -d ' ') bytes)"
echo "Wrote $OUT_DIR/antiek-swarm-review-glmf.txt ($(wc -c < "$OUT_DIR/antiek-swarm-review-glmf.txt" | tr -d ' ') bytes)"
echo "Wrote $OUT_DIR/antiek-swarm-review-grok.txt ($(wc -c < "$OUT_DIR/antiek-swarm-review-grok.txt" | tr -d ' ') bytes)"
