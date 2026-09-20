#!/bin/bash
# Parallel noninteractive PR reviews: claude -p + glmf-codex review + grok --single.
#
# Usage:
#   ./scripts/anti-ek-swarm-review.sh --check           # readiness smoke (no model calls)
#   ./scripts/anti-ek-swarm-review.sh --dry-run [base]  # write diff + plan only
#   ./scripts/anti-ek-swarm-review.sh [base-ref]        # parallel reviews
#
# Writes /tmp/antiek-swarm-review-{claude,glmf,grok}.txt — no secrets.
# Cite: docs/anti-ek-cli-swarm.md ; docs/decisions/cli-herdr-swarm-ready-2026-09-19.md
set -euo pipefail
# PATH discipline (#3181): ~/.local/bin BEFORE Homebrew so Claude 2.1.x wins brew.
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

_git_short() {
  local dir="$1"
  if [[ -d "$dir/.git" ]] || git -C "$dir" rev-parse --git-dir >/dev/null 2>&1; then
    git -C "$dir" rev-parse --short HEAD 2>/dev/null || echo "?"
  else
    echo "not-a-git-dir"
  fi
}

_check() {
  {
    echo "anti-ek-swarm-check $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "host=$(hostname 2>/dev/null || echo unknown)"
    echo "cwd=$ROOT"
    echo "cwd_tip=$(_git_short "$ROOT")"
    echo "PATH_ok=$( [[ ":$PATH:" == *":$HOME/.local/bin:"* ]] && echo yes || echo no )"
    _local_idx=$(awk -v RS=: -v p="$HOME/.local/bin" '{if($0==p){print NR; exit}}' <<<"$PATH")
    _brew_idx=$(awk -v RS=: -v p="/opt/homebrew/bin" '{if($0==p){print NR; exit}}' <<<"$PATH")
    if [[ -n "${_local_idx:-}" && ( -z "${_brew_idx:-}" || $_local_idx -lt $_brew_idx ) ]]; then
      echo "PATH_local_before_brew=yes"
    else
      echo "PATH_local_before_brew=no"
    fi
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
        # Focused workspace honesty (do not invent labels).
        if command -v python3 >/dev/null 2>&1; then
          python3 - "$OUT_DIR/antiek-herdr-workspaces.json" <<'PY' || true
import json, sys
path = sys.argv[1]
try:
    data = json.load(open(path))
except Exception as e:
    print(f"WARN herdr workspace JSON parse failed: {e}")
    raise SystemExit(0)
workspaces = data.get("result", data).get("workspaces", data.get("workspaces", []))
focused = [w for w in workspaces if w.get("focused")]
if focused:
    w = focused[0]
    print(f"OK  focused_workspace={w.get('workspace_id')} label={w.get('label')!r} tabs={w.get('tab_count')}")
else:
    print("WARN no focused herdr workspace (UI idle?)")
antiek = [w for w in workspaces if w.get("workspace_id") == "w7" or w.get("label") == "Antiek"]
if antiek:
    w = antiek[0]
    print(f"OK  antiek_tabs={w.get('tab_count')} panes={w.get('pane_count')} focused={bool(w.get('focused'))}")
PY
        fi
      else
        echo "WARN herdr workspace list failed (server down?)"
      fi
      if herdr tab list >"$OUT_DIR/antiek-herdr-tabs.json" 2>/dev/null; then
        if command -v python3 >/dev/null 2>&1; then
          python3 - "$OUT_DIR/antiek-herdr-tabs.json" <<'PY' || true
import json, sys, re
path = sys.argv[1]
try:
    data = json.load(open(path))
except Exception as e:
    print(f"WARN herdr tab JSON parse failed: {e}")
    raise SystemExit(0)
tabs = data.get("result", data).get("tabs", data.get("tabs", []))
w7 = [t for t in tabs if t.get("workspace_id") == "w7"]
labels = [str(t.get("label") or "") for t in sorted(w7, key=lambda x: x.get("number") or 0)]
print(f"OK  w7_tab_count={len(w7)}")
if labels:
    print("OK  w7_tab_labels=" + ",".join(labels))
# Soft role-tab honesty — WARN only; never invent/rename tabs.
role_res = {
    "claude": re.compile(r"^claude$", re.I),
    "glmf|codex|glm": re.compile(r"^(glmf|glm|codex)(-|$|\d)", re.I),
    "herdr": re.compile(r"^herdr$", re.I),
}
lower = [l.lower() for l in labels]
for name, rx in role_res.items():
    if any(rx.search(l) for l in lower):
        print(f"OK  w7_role_tab~={name}")
    else:
        print(f"WARN w7 missing role-ish tab matching {name} (observed only; do not auto-create)")
PY
        else
          echo "WARN python3 missing — cannot summarize w7 tabs"
        fi
      else
        echo "WARN herdr tab list failed"
      fi
    else
      echo "MISS herdr"
    fi
    echo
    echo "## Dogfood worktrees (preferred first)"
    # Tip-sync probe is the Anti-Ek recursive-perfection dogfood tree.
    # deploy-main / legacy .worktrees remain OK when present but may lag tip.
    local preferred_ok=0
    for wt in \
      "/private/tmp/antiek-main-probe" \
      "/Users/slimydog/Antiek/deploy-main-20260917" \
      "/Users/slimydog/Antiek/.worktrees/anti-ek-use-main-20260917"; do
      if [[ -d "$wt" ]]; then
        echo "OK  $wt (tip=$(_git_short "$wt"))"
        if [[ "$wt" == "/private/tmp/antiek-main-probe" ]]; then
          preferred_ok=1
        fi
      else
        echo "MISS $wt"
      fi
    done
    if [[ $preferred_ok -eq 0 ]]; then
      echo "WARN preferred tip-sync probe /private/tmp/antiek-main-probe missing — use deploy-main or create probe"
    fi
    if [[ -d "/Users/slimydog/Antiek/platform" ]]; then
      echo "OK  /Users/slimydog/Antiek/platform (ansible inventory + .venv)"
    else
      echo "MISS /Users/slimydog/Antiek/platform"
    fi
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

# Full branch diff by default. (Legacy books/upload specialty path retired —
# it silently under-scoped Anti-Ek PRs outside that era.)
git diff "${BASE}...HEAD" > "$DIFF_FILE" || : > "$DIFF_FILE"

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
