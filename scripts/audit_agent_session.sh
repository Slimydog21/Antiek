#!/usr/bin/env bash
# ANT-EXEC-H2V SPR-04 — grep gate for forbidden handoff patterns (F1, F3).
#
# Audits agent session handoff markdown (see docs/agent-execution/HARD_TO_VARY.md).
# Complements tools/agent/verify_handoff.ts (schema); this script catches theater
# strings grep can falsify without a full parser.
#
# USAGE
#   scripts/audit_agent_session.sh handoff.md [handoff2.md ...]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
FAIL=0

usage() {
  echo "Usage: audit_agent_session.sh <handoff.md> ..." >&2
  exit 2
}

[[ $# -gt 0 ]] || usage

has_scope_map() {
  local f="$1"
  rg -q '^(###|##) Scope Map$' "$f" \
    || rg -q 'PLATFORM_EXEC_MATRIX' "$f"
}

audit_file() {
  local f="$1"
  if [[ ! -f "$f" ]]; then
    echo "FAIL: not a file: $f" >&2
    FAIL=1
    return
  fi

  # F1 — pytest piped to tail (verification theater; egghead lineage)
  if rg -n 'pytest\b[^|\n]*\|\s*tail\b' "$f" >/dev/null 2>&1; then
    echo "FAIL [$f] F1: pytest piped to tail — retain full log path (HARD_TO_VARY F1)" >&2
    FAIL=1
  fi

  # F3 — unbounded platform OK without Scope Map / PLATFORM_EXEC_MATRIX
  if rg -ni 'platform\s+ok|engine\s+fine(\s+across|\s+on)?\s+(the\s+)?platform' "$f" >/dev/null 2>&1; then
    if ! has_scope_map "$f"; then
      echo "FAIL [$f] F3: platform OK / engine fine without ### Scope Map or PLATFORM_EXEC_MATRIX (F3)" >&2
      FAIL=1
    fi
  fi
}

for f in "$@"; do
  audit_file "$f"
done

if [[ "$FAIL" -eq 0 ]]; then
  echo "AUDIT_OK: handoff session patterns ($# file(s))"
fi
exit "$FAIL"