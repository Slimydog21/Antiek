#!/usr/bin/env bash
# ANT-H2V SPR-06 — grep gate for decomposer contract drift.
# Audited paths only (not every render_full_prompt in the repo).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
FAIL=0

# ripgrep on dev machines; POSIX grep on ubuntu-latest CI (no rg in PATH by default).
file_line_matches() {
  local pattern="$1" file="$2"
  if command -v rg >/dev/null 2>&1; then
    rg -n "$pattern" "$file" 2>/dev/null || true
  else
    grep -nE "$pattern" "$file" 2>/dev/null || true
  fi
}

file_has_match() {
  local pattern="$1" file="$2"
  if command -v rg >/dev/null 2>&1; then
    rg -q "$pattern" "$file"
  else
    grep -qE "$pattern" "$file"
  fi
}

check_no_positional_render() {
  local file="$1"
  local hits
  hits="$(
    file_line_matches 'render_full_prompt[[:space:]]*\([[:space:]]*[^*]' "$file" \
      | grep -vE 'render_full_prompt[[:space:]]*\([[:space:]]*$' \
      | grep -vE '^[[:space:]]*#' || true
  )"
  if [[ -n "$hits" ]]; then
    echo "FAIL: possible positional render_full_prompt in $file"
    FAIL=1
  fi
}

for f in \
  roles/cascade_planner/planner.py \
  interfaces/research/api/decomposer.py; do
  if [[ -f "$f" ]]; then
    check_no_positional_render "$f"
  fi
done

# dispatch must receive investigation_id= in planner production path
if ! file_has_match 'dispatch\(.*investigation_id=' roles/cascade_planner/planner.py; then
  echo "FAIL: DispatchDecomposer missing investigation_id= on dispatch()"
  FAIL=1
fi

if [[ "$FAIL" -eq 0 ]]; then
  echo "AUDIT_OK: decomposer call sites in audited files"
fi
exit "$FAIL"